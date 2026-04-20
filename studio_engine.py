#!/usr/bin/env python3
"""
Holodeck Studio — Where ideas actualize.

NOT a simulation. Every room connects to LIVE systems.
When you run a command in the studio, it hits the real thing.
"""
import json
import os
import subprocess
import urllib.error
import urllib.request
import base64
import hashlib
from datetime import datetime, timezone
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from pathlib import Path

class LiveConnection:
    """Represents a connection to an external live system.
    
    Supports connections to GitHub, Keeper API, shell commands,
    and generic HTTP endpoints.
    """
    
    def __init__(self, name: str, conn_type: str, config: Dict[str, Any]) -> None:
        """Initialize a live connection.
        
        Args:
            name: Connection identifier
            conn_type: Type of connection (github, keeper, shell, http)
            config: Configuration dictionary for the connection
        """
        self.name = name
        self.conn_type = conn_type
        self.config = config
        self.status = "disconnected"
        self.error_log: List[str] = []
    
    def connect(self) -> Dict[str, str]:
        """Attempt to establish the connection.
        
        Returns:
            Dictionary with 'status' key ('connected' or 'error')
            and additional connection-specific data
        """
        try:
            if self.conn_type == "github":
                token = self.config.get("token") or os.environ.get("GITHUB_TOKEN","")
                r = urllib.request.Request("https://api.github.com/user", 
                    headers={"Authorization": f"token {token}"})
                with urllib.request.urlopen(r, timeout=10) as resp:
                    user = json.loads(resp.read())
                self.status = "connected"
                return {"status":"connected","user":user.get("login","?")}
            elif self.conn_type == "keeper":
                url = self.config.get("url","http://127.0.0.1:8900")
                r = urllib.request.Request(f"{url}/health")
                with urllib.request.urlopen(r, timeout=5) as resp:
                    d = json.loads(resp.read())
                self.status = "connected"
                return {"status":"connected","version":d.get("version","?")}
            elif self.conn_type == "shell":
                self.status = "connected"
                return {"status":"connected","host":os.uname().nodename}
            elif self.conn_type == "http":
                url = self.config.get("url","")
                urllib.request.urlopen(urllib.request.Request(url), timeout=5)
                self.status = "connected"
                return {"status":"connected","url":url}
        except urllib.error.HTTPError as e:
            self.status = "error"
            self.error_log.append(f"HTTP {e.code}: {str(e)[:60]}")
            return {"status":"error","message":f"HTTP {e.code}"}
        except urllib.error.URLError as e:
            self.status = "error"
            self.error_log.append(f"Network: {str(e)[:60]}")
            return {"status":"error","message":"Network error"}
        except json.JSONDecodeError as e:
            self.status = "error"
            self.error_log.append(f"JSON: {str(e)[:60]}")
            return {"status":"error","message":"Invalid JSON response"}
        except OSError as e:
            self.status = "error"
            self.error_log.append(f"OS: {str(e)[:60]}")
            return {"status": "error", "message": f"OS error: {str(e)[:40]}"}
        except Exception as e:
            self.status = "error"
            self.error_log.append(f"Unexpected: {str(e)[:60]}")
            return {"status":"error","message":"Connection failed"}
    
    def execute(self, command: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a command through this connection.
        
        Args:
            command: The command to execute
            params: Optional command parameters
            
        Returns:
            Dictionary with command result or error information
        """
        params = params or {}
        try:
            if self.conn_type == "github": 
                return self._github(command, params)
            elif self.conn_type == "keeper": 
                return self._keeper(command, params)
            elif self.conn_type == "shell": 
                return self._shell(command, params)
            elif self.conn_type == "http": 
                return self._http(command, params)
            else:
                return {"status":"error","message":"Unknown connection type"}
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
    
    def _keeper(self, cmd: str, p: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Keeper API command.
        
        Args:
            cmd: Keeper command to execute
            p: Command parameters
            
        Returns:
            Result dictionary from Keeper API
        """
        url = self.config.get("url","http://127.0.0.1:8900")
        h = {"Content-Type":"application/json"}
        if p.get("agent_id"): h["X-Agent-ID"] = p["agent_id"]
        if p.get("secret"): h["X-Agent-Secret"] = p["secret"]
        body = json.dumps(p.get("body",{})).encode() if p.get("body") else None
        method = p.get("method","GET")
        path = p.get("path","/")
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{url}{path}",data=body,headers=h,method=method),timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return {"status":"error","message":f"Keeper API error {e.code}","code":e.code}
        except (urllib.error.URLError, TimeoutError) as e:
            return {"status":"error","message":"Keeper API unreachable"}
        except json.JSONDecodeError as e:
            return {"status":"error","message":"Invalid Keeper response"}
        except Exception as e:
            return {"status":"error","message":str(e)[:80]}
    
    def _shell(self, cmd: str, p: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a shell command.
        
        Args:
            cmd: Shell command (often superseded by params)
            p: Command parameters including the actual command
            
        Returns:
            Result dictionary with stdout/stderr
        """
        try:
            result = subprocess.run(p.get("cmd",cmd),shell=True,capture_output=True,text=True,timeout=p.get("timeout",30))
            return {"status": "ok" if result.returncode == 0 else "error", "stdout": result.stdout[:2000], "stderr": result.stderr[:500]}
        except subprocess.TimeoutExpired:
            return {"status":"error","message":"Command timed out"}
        except subprocess.CalledProcessError as e:
            return {"status":"error","message":f"Command failed: {str(e)[:60]}","stderr":e.stderr[:500] if e.stderr else ""}
        except Exception as e:
            return {"status":"error","message":str(e)[:80]}
    
    def _http(self, cmd: str, p: Dict[str, Any]) -> Dict[str, Any]:
        """Execute generic HTTP request.
        
        Args:
            cmd: HTTP command
            p: Request parameters including URL, method, headers, and body
            
        Returns:
            Result dictionary with response data
        """
        try:
            url = p.get("url",self.config.get("url",""))
            body = json.dumps(p.get("body",{})).encode() if p.get("body") else None
            with urllib.request.urlopen(urllib.request.Request(url,data=body,headers=p.get("headers",{}),method=p.get("method","POST")),timeout=30) as r:
                return {"status":"ok","response":r.read()[:2000].decode()}
        except urllib.error.HTTPError as e:
            return {"status":"error","message":f"HTTP error {e.code}","code":e.code}
        except (urllib.error.URLError, TimeoutError) as e:
            return {"status":"error","message":"HTTP request failed"}
        except Exception as e:
            return {"status":"error","message":str(e)[:80]}

@dataclass
class StudioRoom:
    """Represents a room in the Holodeck Studio.
    
    Attributes:
        id: Unique room identifier
        name: Display name of the room
        description: Text description of the room's purpose
        room_type: Category of room (deployment, monitoring, etc.)
        connection: Optional LiveConnection to external system
        commands: Dictionary mapping command names to info
        state: Arbitrary room state dictionary
    """
    id: str
    name: str
    description: str
    room_type: str
    connection: Optional[LiveConnection] = None
    commands: Dict[str, dict] = field(default_factory=dict)
    state: dict = field(default_factory=dict)

class Studio:
    """Manages the Holodeck Studio and its rooms.
    
    The Studio is a collection of rooms, each potentially connected
    to live external systems like GitHub, Keeper API, or shell.
    """
    
    def __init__(self) -> None:
        """Initialize the Studio."""
        self.rooms: Dict[str, StudioRoom] = {}
        self.log: List[dict] = []
    
    def add_room(self, room: StudioRoom) -> None:
        """Add a room to the studio.
        
        Args:
            room: StudioRoom to add
        """
        self.rooms[room.id] = room
    
    def connect_all(self) -> List[tuple[Dict[str, str], str]]:
        """Attempt to connect all rooms to their external systems.
        
        Returns:
            List of tuples containing (connection result, room name)
        """
        return [(r.connect(), r.name) for r in self.rooms.values()]
    
    def enter(self, room_id: str, agent: str) -> str:
        """Enter a room and show its information.
        
        Args:
            room_id: ID of the room to enter
            agent: Name of the agent entering (for logging)
            
        Returns:
            Formatted string describing the room
        """
        room = self.rooms.get(room_id)
        if not room:
            return f"No room '{room_id}'."
        conn = room.state.get("connection", {})
        live = "🟢 LIVE" if conn.get("status") in ("connected", "reachable") else "🔴 OFFLINE"
        lines = [f"═══ {room.name} ═══", room.description, "", f"{live}"]
        if room.commands:
            lines.append("Commands:")
            for c, i in room.commands.items():
                lines.append(f"  {c:20s} — {i.get('desc', '')}")
        return "\n".join(lines)
    
    def execute(self, room_id: str, command: str, params: Optional[Dict[str, Any]] = None, agent: str = "") -> Dict[str, Any]:
        """Execute a command in a specific room.
        
        Args:
            room_id: ID of the room
            command: Command to execute
            params: Optional command parameters
            agent: Optional agent name for logging
            
        Returns:
            Result dictionary from the command execution
        """
        room = self.rooms.get(room_id)
        if not room or not room.connection:
            return {"error": "no room/connection"}
        result = room.connection.execute(command, params or {})
        self.log.append({"agent": agent, "room": room_id, "cmd": command, "ts": datetime.now(timezone.utc).isoformat()})
        return result

def build_studio() -> Studio:
    """Build and return a default Holodeck Studio configuration.
    
    Creates rooms for Harbor, Lighthouse, Engine Room, and Workshop,
    each connected to appropriate live systems.
    
    Returns:
        Configured Studio instance
    """
    s = Studio()
    s.add_room(StudioRoom("harbor", "The Harbor", "Live GitHub — create repos, push files, manage fleet", "deployment",
        LiveConnection("github", "github", {}), {"create_repo": {"desc": "Create repo"}, "write_file": {"desc": "Write file"}, "list_repos": {"desc": "List repos"}}))
    s.add_room(StudioRoom("lighthouse", "The Lighthouse", "Live Keeper — fleet monitoring, I2I, batons", "monitoring",
        LiveConnection("keeper", "keeper", {"url": "http://127.0.0.1:8900"}), {"health": {"desc": "Keeper health"}, "register": {"desc": "Register agent"}}))
    s.add_room(StudioRoom("engine", "The Engine Room", "Live shell — build, test, deploy on the metal", "infrastructure",
        LiveConnection("shell", "shell", {}), {"run": {"desc": "Run command"}, "build": {"desc": "Build project"}}))
    s.add_room(StudioRoom("workshop", "The Workshop", "Live LLM API — generate, review, fix code", "development",
        LiveConnection("http", "http", {"url": "https://api.z.ai/api/coding/paas/v4/chat/completions"}), {"generate": {"desc": "Generate code"}, "review": {"desc": "Review code"}}))
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
