#!/usr/bin/env python3
"""
Holodeck Studio — Where ideas actualize.

NOT a simulation. Every room connects to LIVE systems.
When you run a command in the studio, it hits the real thing.
"""
import json, os, subprocess, urllib.request, base64, time, hashlib
from datetime import datetime, timezone
from typing import Dict, Optional
from dataclasses import dataclass, field
from pathlib import Path

class LiveConnection:
    def __init__(self, name, conn_type, config):
        self.name = name; self.conn_type = conn_type; self.config = config
        self.status = "disconnected"; self.error_log = []
    
    def connect(self):
        try:
            if self.conn_type == "github":
                token = self.config.get("token") or os.environ.get("GITHUB_TOKEN","")
                r = urllib.request.Request("https://api.github.com/user", 
                    headers={"Authorization": f"token {token}"})
                user = json.loads(urllib.request.urlopen(r,timeout=10).read())
                self.status = "connected"
                return {"status":"connected","user":user.get("login","?")}
            elif self.conn_type == "keeper":
                url = self.config.get("url","http://127.0.0.1:8900")
                r = urllib.request.Request(f"{url}/health")
                d = json.loads(urllib.request.urlopen(r,timeout=5).read())
                self.status = "connected"
                return {"status":"connected","version":d.get("version","?")}
            elif self.conn_type == "shell":
                self.status = "connected"
                return {"status":"connected","host":os.uname().nodename}
            elif self.conn_type == "http":
                url = self.config.get("url","")
                urllib.request.urlopen(urllib.request.Request(url),timeout=5)
                self.status = "connected"
                return {"status":"connected","url":url}
        except Exception as e:
            self.status = "error"; return {"status":"error","message":str(e)[:60]}
    
    def execute(self, command, params=None):
        params = params or {}
        try:
            if self.conn_type == "github": return self._github(command, params)
            elif self.conn_type == "keeper": return self._keeper(command, params)
            elif self.conn_type == "shell": return self._shell(command, params)
            elif self.conn_type == "http": return self._http(command, params)
        except Exception as e:
            return {"status":"error","command":command,"message":str(e)[:100]}
    
    def _github(self, cmd, p):
        token = self.config.get("token") or os.environ.get("GITHUB_TOKEN","")
        h = {"Authorization":f"token {token}","Content-Type":"application/json"}
        if cmd == "list_repos":
            url = f"https://api.github.com/users/{p.get('owner','SuperInstance')}/repos?per_page={p.get('limit',10)}"
            repos = json.loads(urllib.request.urlopen(urllib.request.Request(url,headers=h),timeout=15).read())
            return {"status":"listed","count":len(repos),"repos":[{"name":r["name"],"desc":r.get("description","")} for r in repos]}
        elif cmd == "create_repo":
            body = json.dumps({"name":p["name"],"description":p.get("description",""),"auto_init":True}).encode()
            r = json.loads(urllib.request.urlopen(urllib.request.Request("https://api.github.com/user/repos",data=body,headers=h,method="POST"),timeout=15).read())
            return {"status":"created","repo":r["full_name"],"url":r["html_url"]}
        elif cmd == "write_file":
            repo,path,content = p["repo"],p["path"],p["content"]
            c = base64.b64encode(content.encode()).decode()
            try:
                ex = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://api.github.com/repos/{repo}/contents/{path}",headers=h),timeout=10).read())
                body = json.dumps({"message":p.get("message","studio"),"content":c,"sha":ex["sha"]}).encode()
            except: body = json.dumps({"message":p.get("message","studio"),"content":c}).encode()
            urllib.request.urlopen(urllib.request.Request(f"https://api.github.com/repos/{repo}/contents/{path}",data=body,headers=h,method="PUT"),timeout=15)
            return {"status":"written","path":path}
    
    def _keeper(self, cmd, p):
        url = self.config.get("url","http://127.0.0.1:8900")
        h = {"Content-Type":"application/json"}
        if p.get("agent_id"): h["X-Agent-ID"] = p["agent_id"]
        if p.get("secret"): h["X-Agent-Secret"] = p["secret"]
        body = json.dumps(p.get("body",{})).encode() if p.get("body") else None
        method = p.get("method","GET")
        path = p.get("path","/")
        return json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}{path}",data=body,headers=h,method=method),timeout=15).read())
    
    def _shell(self, cmd, p):
        r = subprocess.run(p.get("cmd",cmd),shell=True,capture_output=True,text=True,timeout=p.get("timeout",30))
        return {"status":"ok" if r.returncode==0 else "error","stdout":r.stdout[:2000],"stderr":r.stderr[:500]}
    
    def _http(self, cmd, p):
        url = p.get("url",self.config.get("url",""))
        body = json.dumps(p.get("body",{})).encode() if p.get("body") else None
        r = urllib.request.urlopen(urllib.request.Request(url,data=body,headers=p.get("headers",{}),method=p.get("method","POST")),timeout=30)
        return {"status":"ok","response":r.read()[:2000].decode()}

@dataclass
class StudioRoom:
    id: str; name: str; description: str; room_type: str
    connection: Optional[LiveConnection] = None
    commands: Dict[str, dict] = field(default_factory=dict)
    state: dict = field(default_factory=dict)

class Studio:
    def __init__(self):
        self.rooms: Dict[str, StudioRoom] = {}
        self.log = []
    
    def add_room(self, room):
        self.rooms[room.id] = room
    
    def connect_all(self):
        return [(r.connect(), r.name) for r in self.rooms.values()]
    
    def enter(self, room_id, agent):
        room = self.rooms.get(room_id)
        if not room: return f"No room '{room_id}'."
        conn = room.state.get("connection",{})
        live = "🟢 LIVE" if conn.get("status") in ("connected","reachable") else "🔴 OFFLINE"
        lines = [f"═══ {room.name} ═══", room.description,"",f"{live}"]
        if room.commands:
            lines.append("Commands:")
            for c,i in room.commands.items(): lines.append(f"  {c:20s} — {i.get('desc','')}")
        return "\n".join(lines)
    
    def execute(self, room_id, command, params=None, agent=""):
        room = self.rooms.get(room_id)
        if not room or not room.connection: return {"error":"no room/connection"}
        result = room.connection.execute(command, params or {})
        self.log.append({"agent":agent,"room":room_id,"cmd":command,"ts":datetime.now(timezone.utc).isoformat()})
        return result

def build_studio():
    s = Studio()
    s.add_room(StudioRoom("harbor","The Harbor","Live GitHub — create repos, push files, manage fleet","deployment",
        LiveConnection("github","github",{}),{"create_repo":{"desc":"Create repo"},"write_file":{"desc":"Write file"},"list_repos":{"desc":"List repos"}}))
    s.add_room(StudioRoom("lighthouse","The Lighthouse","Live Keeper — fleet monitoring, I2I, batons","monitoring",
        LiveConnection("keeper","keeper",{"url":"http://127.0.0.1:8900"}),{"health":{"desc":"Keeper health"},"register":{"desc":"Register agent"}}))
    s.add_room(StudioRoom("engine","The Engine Room","Live shell — build, test, deploy on the metal","infrastructure",
        LiveConnection("shell","shell",{}),{"run":{"desc":"Run command"},"build":{"desc":"Build project"}}))
    s.add_room(StudioRoom("workshop","The Workshop","Live LLM API — generate, review, fix code","development",
        LiveConnection("http","http",{"url":"https://api.z.ai/api/coding/paas/v4/chat/completions"}),{"generate":{"desc":"Generate code"},"review":{"desc":"Review code"}}))
    return s

if __name__ == "__main__":
    print("╔══════════════════════════════════════════╗")
    print("║  HOLODECK STUDIO — Where Ideas Actualize ║")
    print("╚══════════════════════════════════════════╝\n")
    studio = build_studio()
    print("🔌 Connecting to live systems...")
    for status, name in studio.connect_all():
        print(f"  {status.get('status','?'):12s} {name}")
    print(f"\n{studio.enter('harbor','oracle1')}\n")
    r = studio.execute("harbor","list_repos",{"owner":"SuperInstance","limit":5})
    if r.get("status")=="listed":
        print(f"📋 {r['count']} repos found. First 5:")
        for repo in r["repos"]: print(f"  - {repo['name']}")
    print(f"\n{studio.enter('lighthouse','oracle1')}\n")
    r = studio.execute("lighthouse","health",{"method":"GET","path":"/health"})
    print(f"🩺 Keeper: {r.get('status')} v{r.get('version')} ({r.get('agents')} agents)")
    print(f"\n{studio.enter('engine','oracle1')}\n")
    r = studio.execute("engine","run",{"cmd":"uptime"})
    print(f"🔧 Host: {r.get('stdout','').strip()}")
    print("\n═══════════════════════════════════")
    print("Every command was REAL. Not simulated.")
    print("The studio actualizes.")
    print("═══════════════════════════════════")
