"""Job queue in SQLite: survives restarts, runs one match at a time, waits out usage limits."""
import json
import sqlite3
import threading
import time
import traceback
from . import CACHE, OUT, tba
from .backends.base import UsageLimit
from .backends import make
from .config import game as load_game, load
from .export import write
from .pipeline import entries_for, process, saved_result, wanted

DB = CACHE / "jobs.db"
_lock = threading.Lock()


def db():
    CACHE.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.executescript("""
    create table if not exists jobs (id integer primary key, event text, start int, end int, teams text,
        status text, created real, paused_until real, message text);
    create table if not exists job_matches (job_id int, match_key text, label text, seq int,
        status text, error text, usage text, primary key (job_id, match_key));
    """)
    return c


def create(event, start, end, teams, rescout=False):
    ms = tba.select(event, start, end, teams)
    with _lock, db() as c:
        cur = c.execute("insert into jobs (event, start, end, teams, status, created) values (?,?,?,?,?,?)",
                        (event, start, end, json.dumps(teams or []), "queued", time.time()))
        jid = cur.lastrowid
        for i, m in enumerate(ms):
            done = not rescout and saved_result(m, wanted(m, teams))
            c.execute("insert into job_matches values (?,?,?,?,?,?,?)",
                      (jid, m["key"], tba.label(m), i, "done" if done else "queued", None, None))
    return jid


def jobs():
    with db() as c:
        out = []
        for j in c.execute("select * from jobs order by id desc"):
            ms = [dict(r) for r in c.execute("select * from job_matches where job_id=? order by seq", (j["id"],))]
            out.append(dict(j, teams=json.loads(j["teams"]), matches=ms))
        return out


def cancel(jid):
    with _lock, db() as c:
        c.execute("update jobs set status='cancelled' where id=?", (jid,))
        c.execute("update job_matches set status='cancelled' where job_id=? and status in ('queued','running')", (jid,))


def clear_finished():
    """Remove done/cancelled jobs from the list. Saved match results and import files are kept."""
    with _lock, db() as c:
        ids = [r[0] for r in c.execute("select id from jobs where status in ('done','cancelled')")]
        c.executemany("delete from job_matches where job_id=?", [(i,) for i in ids])
        c.executemany("delete from jobs where id=?", [(i,) for i in ids])
    return len(ids)


def export(jid):
    """Write the import file for every finished match in a job; returns its path."""
    with db() as c:
        j = c.execute("select * from jobs where id=?", (jid,)).fetchone()
        keys = [r["match_key"] for r in c.execute(
            "select match_key from job_matches where job_id=? and status='done' order by seq", (jid,))]
    teams = json.loads(j["teams"]) or None
    game = load_game(int(j["event"][:4]))
    entries = []
    for k in keys:
        m = tba.match(k)
        res = saved_result(m, wanted(m, teams))
        if res:
            entries += entries_for(m, res, game, res.get("backend", "claude-code"), wanted(m, teams))
    return write(entries, f"{j['event']}-job{jid}"), len(entries)


class Worker(threading.Thread):
    """Takes the oldest queued match of the oldest active job, one at a time."""
    daemon = True

    def __init__(self):
        super().__init__()
        self.log_lines = []

    def log(self, s):
        self.log_lines = (self.log_lines + [time.strftime("%H:%M:%S ") + s])[-200:]

    def next_match(self):
        with _lock, db() as c:
            c.execute("update job_matches set status='queued' where status='running'")   # after a crash/restart
            row = c.execute("""select jm.*, j.event, j.teams, j.paused_until from job_matches jm
                               join jobs j on j.id = jm.job_id
                               where jm.status='queued' and j.status in ('queued','running','paused')
                               order by j.id, jm.seq limit 1""").fetchone()
            if row:
                c.execute("update job_matches set status='running' where job_id=? and match_key=?",
                          (row["job_id"], row["match_key"]))
                c.execute("update jobs set status='running', paused_until=null, message=null where id=?", (row["job_id"],))
            return row

    def finish(self, row, status, error=None, usage=None):
        with _lock, db() as c:
            c.execute("update job_matches set status=?, error=?, usage=? where job_id=? and match_key=?",
                      (status, error, json.dumps(usage) if usage else None, row["job_id"], row["match_key"]))
            left = c.execute("select count(*) from job_matches where job_id=? and status in ('queued','running')",
                             (row["job_id"],)).fetchone()[0]
            if not left:
                c.execute("update jobs set status='done' where id=? and status='running'", (row["job_id"],))
        if not left:
            f, n = export(row["job_id"])
            self.log(f"job {row['job_id']} finished: {n} entries in {f.name}")

    def run(self):
        while True:
            try:
                self.step()
            except Exception:
                self.log("worker error: " + traceback.format_exc(limit=2))
                time.sleep(10)

    def step(self):
        row = self.next_match()
        if not row:
            time.sleep(3)
            return
        teams = json.loads(row["teams"]) or None
        m = tba.match(row["match_key"])
        game = load_game(int(row["event"][:4]))
        backend = make(load())
        self.log(f"job {row['job_id']} {row['label']}: scouting")
        try:
            process(m, game, backend, teams, log=self.log)
            usage = json.loads((CACHE / "matches" / m["key"] / "result.json").read_text()).get("usage")
            self.finish(row, "done", usage=usage)
        except UsageLimit as ex:
            until = ex.resume_at or time.time() + 1800
            with _lock, db() as c:
                c.execute("update job_matches set status='queued' where job_id=? and match_key=?",
                          (row["job_id"], row["match_key"]))
                c.execute("update jobs set status='paused', paused_until=?, message=? where id=?",
                          (until, str(ex)[:300], row["job_id"]))
            self.log(f"usage limit: pausing until {time.strftime('%a %H:%M', time.localtime(until))}")
            while time.time() < until:
                time.sleep(30)
        except Exception as ex:
            self.log(f"  failed: {ex}")
            self.finish(row, "failed", error=str(ex)[:500])


OUT.mkdir(parents=True, exist_ok=True)
