import sqlite3, argparse, json, time
from array import array

def build(db):
 t=time.time(); con=sqlite3.connect(db); con.execute('PRAGMA synchronous=OFF'); con.execute('PRAGMA journal_mode=OFF')
 con.execute('CREATE TABLE IF NOT EXISTS series(code TEXT PRIMARY KEY, dates BLOB NOT NULL, closes BLOB NOT NULL)'); con.execute('DELETE FROM series')
 cur=con.execute('SELECT code,date,close FROM stock ORDER BY code,date'); current=None; ds=array('I'); ps=array('d'); n=0; codes=0
 def flush():
  nonlocal ds,ps,codes
  if current is not None:
   con.execute('INSERT INTO series VALUES (?,?,?)',(current,ds.tobytes(),ps.tobytes())); codes+=1
 for c,d,p in cur:
  if c!=current:
   flush(); current=c; ds=array('I'); ps=array('d')
  ds.append(int(d.replace('-',''))); ps.append(float(p)); n+=1
 flush(); con.commit(); con.execute('ANALYZE'); con.commit()
 out={'rows':n,'codes':codes,'seconds':round(time.time()-t,2)}; print(json.dumps(out)); con.close(); return out
if __name__=='__main__':
 ap=argparse.ArgumentParser(); ap.add_argument('db'); a=ap.parse_args(); build(a.db)
