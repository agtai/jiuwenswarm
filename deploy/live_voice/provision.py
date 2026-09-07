"""Generate ten isolated test instances on an already prepared Linux host.

Run as root. The Speech-only input is root/private/speech.json. Outputs with
credentials stay private; stdout contains only public deployment metadata.
No existing model, task, project, password or authorization file is overwritten.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import grp
import html
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import subprocess


def write(path: Path, content: str, mode: int = 0o600, uid: int = 0, gid: int = 0):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(content, encoding='utf-8')
    os.chmod(temporary, mode)
    os.chown(temporary, uid, gid)
    temporary.replace(path)


def provision(root: Path, address: str, suffix: str, image: str):
    if os.geteuid() != 0 or not root.is_absolute():
        raise ValueError('root_and_absolute_directory_required')
    ipaddress.IPv4Address(address)
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,240}[a-z0-9]', suffix):
        raise ValueError('invalid_domain_suffix')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.:/@-]{1,200}', image):
        raise ValueError('invalid_image')
    private = root / 'private'
    private.mkdir(exist_ok=True)
    private.chmod(0o700)
    speech = json.loads((private / 'speech.json').read_text())
    if set(speech) != {'LIVE_VOICE_SPEECH_API_KEY', 'LIVE_VOICE_SPEECH_API_BASE',
                       'LIVE_VOICE_SPEECH_STT_MODEL', 'LIVE_VOICE_SPEECH_TTS_MODEL'}:
        raise ValueError('speech_only_configuration_required')
    auth = root / 'auth'
    auth.mkdir(exist_ok=True)
    web_gid = grp.getgrnam('www-data').gr_gid
    os.chown(auth, 0, web_gid)
    auth.chmod(0o750)
    credentials_file = private / 'tester-access.json'
    credentials = json.loads(credentials_file.read_text()) if credentials_file.exists() else []
    services, networks, servers = {}, {}, []
    expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    for index in range(1, 11):
        name = f'lv{index:02d}'
        hostname = f'{name}.{suffix}'
        existing = [entry for entry in credentials if entry['instance'] == name]
        if len(existing) > 1:
            raise ValueError('duplicate_access_record')
        if existing:
            entry = existing[0]
            if entry['url'] != f'https://{hostname}/':
                raise ValueError('existing_hostname_mismatch')
        else:
            entry = {'instance': name, 'url': f'https://{hostname}/',
                     'username': f'tester{index:02d}', 'password': secrets.token_urlsafe(24)}
            credentials.append(entry)
            # Persist each creation before other side effects, preserving retry identity.
            write(credentials_file, json.dumps(credentials, indent=2) + '\n')
        passwd = auth / (name + '.htpasswd')
        if not passwd.exists():
            result = subprocess.run(['htpasswd', '-niB', entry['username']],
                                    input=entry['password'] + '\n', text=True,
                                    capture_output=True, check=True)
            write(passwd, result.stdout, mode=0o640, gid=web_gid)
        runtime_path = private / (name + '.json')
        if not runtime_path.exists():
            write(runtime_path, json.dumps({'instance': name, 'hostname': hostname,
                  'auth_token': secrets.token_urlsafe(48), 'auth_expires_at': expires,
                  'speech': speech}, indent=2) + '\n', mode=0o400, uid=10001, gid=10001)
        else:
            existing_runtime = json.loads(runtime_path.read_text())
            if existing_runtime.get('instance') != name or existing_runtime.get('hostname') != hostname:
                raise ValueError('runtime_identity_mismatch')
        instance_dir = root / 'instances' / name
        for leaf in ('data', 'projects'):
            directory = instance_dir / leaf
            if not directory.exists():
                directory.mkdir(parents=True)
                os.chown(directory, 10001, 10001)
                directory.chmod(0o700)
        services[name] = {
            'image': image, 'container_name': 'jiuwen-' + name,
            'init': True, 'restart': 'on-failure:3',
            'user': '10001:10001', 'cpus': 2, 'mem_limit': '4g', 'pids_limit': 512,
            'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
            'stop_grace_period': '90s',
            'ports': [f'127.0.0.1:{26100 + index}:5173'],
            'volumes': [f'{instance_dir}/data:/data', f'{instance_dir}/projects:/projects',
                        f'{runtime_path}:/run/secrets/runtime.json:ro'],
            'tmpfs': ['/tmp:size=536870912,mode=1777'], 'networks': [name],
            'logging': {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '3'}},
            'healthcheck': {
                'test': ['CMD', '/app/.venv/bin/python', '-c',
                         'import urllib.request,socket; urllib.request.urlopen("http://127.0.0.1:5173/",timeout=3).read(); [socket.create_connection(("127.0.0.1",p),3).close() for p in (18092,19000,19001)]'],
                'interval': '30s', 'timeout': '10s', 'start_period': '150s', 'retries': 3,
            },
        }
        networks[name] = {'driver': 'bridge'}
        servers.append(f'''server {{
    listen {address}:443 ssl;
    server_name {hostname};
    ssl_certificate /etc/letsencrypt/live/jiuwen-livevoice/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/jiuwen-livevoice/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    auth_basic "JiuwenSwarm {name}";
    auth_basic_user_file {passwd};
    client_max_body_size 50m;
    add_header Permissions-Policy "microphone=(self)" always;
    add_header X-Content-Type-Options nosniff always;
    location / {{
        proxy_pass http://127.0.0.1:{26100 + index};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $jiuwen_connection_upgrade;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering off;
    }}
}}
''')
    compose = {'name': 'jiuwen-livevoice', 'services': services, 'networks': networks}
    write(root / 'compose.json', json.dumps(compose, indent=2) + '\n', mode=0o640)
    domains = [f'swarm.{suffix}'] + [f'lv{i:02d}.{suffix}' for i in range(1, 11)]
    landing = root / 'portal'
    landing.mkdir(exist_ok=True)
    links = ''.join(f'<li><a href="https://lv{i:02d}.{html.escape(suffix)}/">Test environment {i:02d}</a></li>' for i in range(1,11))
    write(landing / 'index.html', '<!doctype html><html lang="en"><meta charset="utf-8">'
          '<meta name="viewport" content="width=device-width,initial-scale=1">'
          '<title>JiuwenSwarm Live Voice</title><body><main><h1>JiuwenSwarm Live Voice Testing</h1>'
          '<p>Open your assigned test environment and sign in with your existing account.</p>'
          '<p>If your administrator has configured the Agent model, you can start testing immediately. '
          'Otherwise, enter the model and API settings under More &rarr; Configuration.</p>'
          '<p>Switch the sidebar from Work to Code. Hover over the Live Voice Test project '
          'and click its plus button to start a new conversation. Enable Live Voice and allow '
          'microphone access in Chrome or Edge.</p>'
          f'<ol>{links}</ol></main></body></html>', mode=0o644)
    header = f'''map $http_upgrade $jiuwen_connection_upgrade {{ default upgrade; '' close; }}
server {{
    listen {address}:80 default_server;
    server_name {' '.join(domains)};
    location ^~ /.well-known/acme-challenge/ {{ root {root}/acme; }}
    location / {{ return 301 https://$host$request_uri; }}
}}
server {{
    listen {address}:443 ssl default_server;
    server_name _;
    ssl_certificate /etc/letsencrypt/live/jiuwen-livevoice/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/jiuwen-livevoice/privkey.pem;
    return 404;
}}
server {{
    listen {address}:443 ssl;
    server_name swarm.{suffix};
    ssl_certificate /etc/letsencrypt/live/jiuwen-livevoice/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/jiuwen-livevoice/privkey.pem;
    root {landing};
    location / {{ try_files $uri $uri/ =404; }}
}}
'''
    write(root / 'nginx.conf', header + '\n'.join(servers), mode=0o644)
    print(json.dumps({'instances': len(services), 'agent_model': 'empty_on_first_use',
                      'native_model': 'gpt-realtime-2', 'portal': f'https://swarm.{suffix}/'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('/srv/jiuwen-livevoice'))
    parser.add_argument('--address', default='192.168.0.88')
    parser.add_argument('--domain-suffix', default='164.30.6.242.sslip.io')
    parser.add_argument('--image', required=True)
    args = parser.parse_args()
    provision(args.root, args.address, args.domain_suffix, args.image)
