#!/usr/bin/env python3
"""
Homelab Dashboard - Monitor all self-hosted services
"""

import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import click
import subprocess

class ServiceStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"

@dataclass
class Service:
    name: str
    url: str
    type: str  # http, tcp, ping, docker
    expected_status: int = 200
    check_interval: int = 60  # seconds
    timeout: int = 5
    
@dataclass
class ServiceCheck:
    service: Service
    status: ServiceStatus
    response_time: float
    last_check: datetime
    error_message: Optional[str] = None

class HomelabDashboard:
    def __init__(self, config_path: str = "services.json"):
        self.config_path = config_path
        self.services: List[Service] = []
        self.checks: Dict[str, ServiceCheck] = {}
        self.load_config()
        
    def load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                self.services = [Service(**s) for s in data.get("services", [])]
        except:
            self.services = self._default_services()
    
    def _default_services(self) -> List[Service]:
        return [
            Service(name="Plex", url="http://localhost:32400", type="http"),
            Service(name="Pi-hole", url="http://localhost/admin", type="http"),
            Service(name="Home Assistant", url="http://localhost:8123", type="http"),
            Service(name="Portainer", url="http://localhost:9000", type="http"),
            Service(name="Nextcloud", url="http://localhost:8080", type="http"),
        ]
    
    async def check_http(self, service: Service) -> ServiceCheck:
        start = datetime.now()
        try:
            timeout = aiohttp.ClientTimeout(total=service.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(service.url) as resp:
                    elapsed = (datetime.now() - start).total_seconds()
                    
                    if resp.status == service.expected_status:
                        status = ServiceStatus.ONLINE
                    else:
                        status = ServiceStatus.DEGRADED
                        
                    return ServiceCheck(
                        service=service,
                        status=status,
                        response_time=elapsed,
                        last_check=datetime.now()
                    )
        except Exception as e:
            return ServiceCheck(
                service=service,
                status=ServiceStatus.OFFLINE,
                response_time=0,
                last_check=datetime.now(),
                error_message=str(e)
            )
    
    async def check_ping(self, service: Service) -> ServiceCheck:
        import platform
        import re
        
        param = "-n" if platform.system().lower() == "windows" else "-c"
        host = service.url.replace("http://", "").replace("https://", "").split(":")[0]
        
        try:
            result = subprocess.run(
                ["ping", param, "1", host],
                capture_output=True,
                timeout=service.timeout
            )
            
            if result.returncode == 0:
                # Extract time
                output = result.stdout.decode()
                time_match = re.search(r'time[=:](\d+(\.\d+)?)\s*ms', output)
                response_time = float(time_match.group(1)) if time_match else 0
                
                return ServiceCheck(
                    service=service,
                    status=ServiceStatus.ONLINE,
                    response_time=response_time,
                    last_check=datetime.now()
                )
        except:
            pass
            
        return ServiceCheck(
            service=service,
            status=ServiceStatus.OFFLINE,
            response_time=0,
            last_check=datetime.now()
        )
    
    async def check_all(self) -> List[ServiceCheck]:
        tasks = []
        for service in self.services:
            if service.type == "http":
                tasks.append(self.check_http(service))
            elif service.type == "ping":
                tasks.append(self.check_ping(service))
                
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, ServiceCheck):
                self.checks[result.service.name] = result
                
        return [r for r in results if isinstance(r, ServiceCheck)]
    
    def get_summary(self) -> Dict:
        total = len(self.checks)
        online = sum(1 for c in self.checks.values() if c.status == ServiceStatus.ONLINE)
        offline = sum(1 for c in self.checks.values() if c.status == ServiceStatus.OFFLINE)
        degraded = sum(1 for c in self.checks.values() if c.status == ServiceStatus.DEGRADED)
        
        return {
            "total": total,
            "online": online,
            "offline": offline,
            "degraded": degraded,
            "uptime_percentage": (online / total * 100) if total > 0 else 0
        }

@click.group()
def cli():
    """Homelab Dashboard CLI"""
    pass

@cli.command()
def check():
    """Check all services"""
    dashboard = HomelabDashboard()
    results = asyncio.run(dashboard.check_all())
    
    print("\n📊 Service Status:")
    print("-" * 60)
    for check in results:
        status_icon = {
            ServiceStatus.ONLINE: "🟢",
            ServiceStatus.OFFLINE: "🔴",
            ServiceStatus.DEGRADED: "🟡",
            ServiceStatus.UNKNOWN: "⚪"
        }.get(check.status, "⚪")
        
        print(f"{status_icon} {check.service.name:20} {check.status.value:10} {check.response_time:.2f}ms")
    
    summary = dashboard.get_summary()
    print("-" * 60)
    print(f"Total: {summary['total']} | 🟢 {summary['online']} | 🔴 {summary['offline']} | 🟡 {summary['degraded']}")
    print(f"Uptime: {summary['uptime_percentage']:.1f}%")

@cli.command()
def serve():
    """Start dashboard web server"""
    print("🌐 Starting Homelab Dashboard on http://localhost:8080")
    print("(Web interface would be served here)")

if __name__ == "__main__":
    cli()
