import os,json,random,secrets,time,threading,sqlite3,re,mimetypes
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
BASE=Path(__file__).resolve().parent
BANK=[]
for line in (BASE/'questions.txt').read_text('utf-8').splitlines():
 p=line.split('|')
 if len(p)==6:BANK.append(dict(topic=p[0],question=p[1],options=p[2:6]))
DB=Path(os.getenv('DB_PATH',str(BASE/'scores.sqlite3')))
DB.parent.mkdir(parents=True,exist_ok=True)
guard=threading.RLock();sessions={}
def connect():
 c=sqlite3.connect(DB,timeout=20)
 c.execute('CREATE TABLE IF NOT EXISTS scores(name TEXT,points INTEGER,accuracy INTEGER,played INTEGER)')
 return c
with connect() as c:pass
def top():
 with connect() as c: rows=c.execute('SELECT name,points,accuracy FROM scores ORDER BY points DESC,accuracy DESC,played ASC LIMIT 30').fetchall()
 return [dict(rank=i+1,name=a,points=b,accuracy=d) for i,(a,b,d) in enumerate(rows)]
def public(q,seq):
 return dict(number=seq+1,total=24,topic=q['topic'],question=q['question'],options=q['options'],stage=seq//8+1,seconds=[22,17,13][seq//8])
class App(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def js(self,status,data):
  raw=json.dumps(data,ensure_ascii=False).encode()
  self.send_response(status);self.send_header('Content-Type','application/json;charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def body(self):
  n=int(self.headers.get('Content-Length','0'))
  if n<0 or n>8192:raise ValueError()
  return json.loads(self.rfile.read(n))
 def do_GET(self):
  route=urlsplit(self.path).path
  if route=='/api/health':return self.js(200,{'ok':True,'questions':len(BANK)})
  if route=='/api/leaderboard':return self.js(200,{'scores':top()})
  if route=='/':route='/index.html'
  if route!='/index.html':return self.send_error(404)
  data=(BASE/'index.html').read_bytes()
  self.send_response(200);self.send_header('Content-Type','text/html;charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
 def do_POST(self):
  try:data=self.body()
  except Exception:return self.js(400,{'error':'Ogiltig begäran'})
  route=urlsplit(self.path).path
  if route=='/api/start':
   name=str(data.get('nickname','')).strip()
   if not re.fullmatch(r'[\w åäöÅÄÖ-]{2,16}',name,re.UNICODE):return self.js(400,{'error':'Ange ett smeknamn på 2–16 tecken'})
   token=secrets.token_urlsafe(24)
   with guard:
    for key,s in list(sessions.items()):
     if time.monotonic()-s['created']>7200:sessions.pop(key,None)
    if len(sessions)>1000:return self.js(503,{'error':'För många spelare just nu'})
    chosen=[]
    for topic in ['GRUND','TROPISK','SUBTROPISK','TEMPERERAD','POLAR','VEGETATION']:
     sample=random.sample([q for q in BANK if q['topic']==topic],4)
     chosen.extend(sample)
    random.shuffle(chosen)
    for q in chosen:
     correct=q['options'][0];random.shuffle(q['options']);q['correct']=q['options'].index(correct)
    sessions[token]=dict(name=name,questions=chosen,idx=0,points=0,streak=0,correct=0,created=time.monotonic(),start=time.monotonic(),bonus=False,bonusStart=0,done=False)
   return self.js(200,{'token':token,'question':public(chosen[0],0),'points':0})
  if route not in ('/api/answer','/api/bonus/start','/api/bonus/finish'):return self.js(404,{'error':'Okänd adress'})
  with guard:
   s=sessions.get(data.get('token'))
   if not s or s['done'] or time.monotonic()-s['created']>7200:return self.js(403,{'error':'Omgången har gått ut'})
   if route=='/api/answer':
    n=s['idx'];option=data.get('choice');number=data.get('number')
    if s['bonus'] or number!=n+1 or type(option)!=int or option not in (-1,0,1,2,3):return self.js(409,{'error':'Ogiltigt val'})
    stage=n//8;secs=[22,17,13][stage];elapsed=time.monotonic()-s['start']
    good=option==s['questions'][n]['correct'] and elapsed<=secs+1
    gain=0
    if good:
     s['correct']+=1;s['streak']+=1
     gain=100+min(100,int(max(0,secs-elapsed)/secs*100))+min(100,(s['streak']-1)*20)+[0,35,75][stage];s['points']+=gain
    else:s['streak']=0
    s['idx']+=1;n=s['idx']
    result={'gain':gain,'points':s['points'],'streak':s['streak']}
    if n==24:
     s['done']=True
     accuracy=round(100*s['correct']/24)
     with connect() as c:c.execute('INSERT INTO scores VALUES(?,?,?,?)',(s['name'],s['points'],accuracy,int(time.time())))
     result.update(finished=True,accuracy=accuracy,leaderboard=top());return self.js(200,result)
    if n in (8,16):
     s['bonus']=True;result.update(bonus=True,stageCompleted=n//8);return self.js(200,result)
    s['start']=time.monotonic();result['question']=public(s['questions'][n],n);return self.js(200,result)
   if route=='/api/bonus/start':
    if not s['bonus'] or s['bonusStart']:return self.js(409,{'error':'Bonus redan startad'})
    s['bonusStart']=time.monotonic();return self.js(200,{'duration':12})
   if route=='/api/bonus/finish':
    if not s['bonus'] or not s['bonusStart'] or time.monotonic()-s['bonusStart']<10:return self.js(409,{'error':'Bonusbanan är inte klar'})
    hits=data.get('hits',0);hits=max(0,min(10,hits if type(hits)==int else 0))
    gain=hits*20;s['points']+=gain;s['bonus']=False;s['bonusStart']=0;s['start']=time.monotonic()
    return self.js(200,{'gain':gain,'points':s['points'],'question':public(s['questions'][s['idx']],s['idx'])})
if __name__=='__main__':
 print('Starting climate quest with',len(BANK),'questions',flush=True)
 ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8000'))),App).serve_forever()
