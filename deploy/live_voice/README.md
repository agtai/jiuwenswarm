# Ten-person Live Voice test deployment

This deployment runs the requested branch in ten independent containers. Each
tester has a separate HTTPS hostname, login, configuration, project and runtime
database. New instances use English and start with empty Agent models. An
administrator can supply Agent settings privately to existing instances;
Native Realtime is explicitly `gpt-realtime-2` with separate Speech credentials.

This is a controlled test installation. Ten connected UIs are distinct from ten
simultaneous completed Agent/voice tasks. Model quotas and a real microphone,
Agent/tool and speaker journey require separate acceptance.

## Build from a committed source

Use a clean server checkout of `codex/deploy-live-voice-ten-user`; record its full
commit. Never include a developer workspace, `.env`, API key, SSH key or DPAPI file in the
build context. Clone directly on the server, or fast-forward an existing clean
checkout, then build there:

```sh
git clone --single-branch --branch codex/deploy-live-voice-ten-user \
  https://github.com/agtai/jiuwenswarm.git /srv/jiuwenswarm
cd /srv/jiuwenswarm
# For subsequent updates: git pull --ff-only
git status --short --branch
git rev-parse HEAD
docker build --build-arg SOURCE_COMMIT=<full-commit> \
  -t jiuwen-livevoice:<commit> -f deploy/live_voice/Dockerfile .
docker image inspect jiuwen-livevoice:<commit> --format '{{.Id}}'
```

The build uses Node 20.20.2, Python 3.12, frozen uv dependencies and
`npm ci && npm run build:live-voice`. Record the resulting immutable image ID;
base image tags and OS repositories can change even with the same application
commit. Use that image ID with `provision.py --image` for the active deployment.

To reproduce the same installed dependencies on another server, transfer the
already verified image over SSH, then verify its image ID after import:

```sh
docker image save --output jiuwen-livevoice-image.tar jiuwen-livevoice:<commit>
# Transfer this archive privately to the destination, then there:
docker image load --input jiuwen-livevoice-image.tar
docker image inspect jiuwen-livevoice:<commit> --format '{{.Id}}'
```

The image contains application code and dependencies. Supply Speech credentials
separately and generate fresh instance data/logins for a new test installation.
Replace the destination interface/DNS values and obtain its HTTPS certificate.

## Host and private configuration

The verified host is Ubuntu 24.04, 32 logical CPUs and 60 GiB RAM. Install
`docker.io docker-compose-v2 docker-buildx nginx apache2-utils certbot`, without
upgrading or restarting unrelated applications. The host needs outbound HTTPS
and WSS to `api.openai.com`; browsers need public TCP 80/443. Only SSH and the
two public web ports need ingress. Do not publish container backend ports.

Use `/srv/jiuwen-livevoice` with root-owned `private` mode 0700. Transfer a JSON
object containing exactly these four values over an authenticated private channel
to `private/speech.json` (root:root, mode 0600):

- `LIVE_VOICE_SPEECH_API_KEY`
- `LIVE_VOICE_SPEECH_API_BASE` (`https://api.openai.com/v1`)
- `LIVE_VOICE_SPEECH_STT_MODEL`
- `LIVE_VOICE_SPEECH_TTS_MODEL`

Keep Agent model credentials in the instance configuration, outside Git and the
image. Do not echo credentials or pass them in command arguments. Remove temporary
plaintext transfer files after installation. The
encrypted Windows sudo file stays on the administrator's computer.

## HTTPS and instance generation

Before changing Nginx/firewall, inspect existing listeners and preserve existing
sites. On an EIP host, Nginx binds the private interface address, not the public
EIP. The current host uses `192.168.0.88`; its Tailscale listener is separate.

For another server, replace both the interface address and DNS suffix. Set up an
HTTP Nginx server on the chosen interface, serving `/.well-known/acme-challenge/`
from `/srv/jiuwen-livevoice/acme`. Obtain one webroot certificate named
`jiuwen-livevoice` for `swarm.<suffix>` and `lv01.<suffix>` through
`lv10.<suffix>`. Example certificate command after HTTP challenge reachability
has been verified (supply an administrator's registration preference):

```sh
certbot certonly --webroot -w /srv/jiuwen-livevoice/acme \
  --cert-name jiuwen-livevoice -d swarm.<suffix> \
  -d lv01.<suffix> -d lv02.<suffix> -d lv03.<suffix> -d lv04.<suffix> \
  -d lv05.<suffix> -d lv06.<suffix> -d lv07.<suffix> -d lv08.<suffix> \
  -d lv09.<suffix> -d lv10.<suffix>
python3 deploy/live_voice/provision.py --root /srv/jiuwen-livevoice \
  --address 192.168.0.88 --domain-suffix 164.30.6.242.sslip.io \
  --image sha256:<verified-image-id>
docker compose -f /srv/jiuwen-livevoice/compose.json config --quiet
install -m 0644 /srv/jiuwen-livevoice/nginx.conf /etc/nginx/sites-available/jiuwen-livevoice
```

Enable that site, run `nginx -t`, and reload Nginx. The generated default servers
must not conflict with an existing default listener on the same address. Preserve
the previous site configuration for rollback. Enable `certbot.timer` and a deploy
hook running `nginx -t && systemctl reload nginx`; verify `certbot renew --dry-run`.

`provision.py` generates ten passwords in `private/tester-access.json` and ten
separate htpasswd files. Transfer the access list privately to the administrator
and give each tester only their own row. Rerunning the generator preserves
passwords, runtime authorizations and all existing user model/project data.

Start one instance first, check its logs/health and browser configuration page,
then start all ten:

```sh
docker compose -f /srv/jiuwen-livevoice/compose.json up -d lv01
docker inspect jiuwen-lv01 --format '{{.State.Health.Status}}'
install -m 0644 deploy/live_voice/jiuwen-livevoice.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now jiuwen-livevoice.service
```

Each container runs as UID 10001, has a separate bridge network, a 2-CPU / 4-GiB
limit, no Linux capabilities, no Docker socket, and only a loopback host port
26101–26110 mapped to its Web UI. Host service startup restores the compose set
after reboot. A process failure has at most three Docker retries. A persistent
Speech or authorization error requires operator diagnosis rather than an endless
retry loop. Health checks cover local services; they do not prove live Provider
quota or microphone/Agent acceptance.

## Tester journey

Open the assigned HTTPS URL and log in. If the administrator has configured the
Agent model, no model setup is needed. Otherwise use **More → Configuration**
to enter the Agent model name, provider, API base and API key, then save and
confirm the model. Switch the left sidebar from **Work** to **Code**, hover over
the **Live Voice Test** project and click its plus button to start a new
conversation, then enable Live Voice.
Allow microphone access in the browser. The server supplies Native Realtime;
testers do not need the shared Speech API key.

Read `inventory.csv`, ask the Agent to create a short report inside that project,
and compare the actual file, task result and spoken response. With no Agent model
configured, model-dependent voice/Agent work is not ready. ASR/TTS connectivity
alone must not be reported as a successful Agent/tool journey.

## English interface and existing instances

The portal is generated in English by `provision.py`. Change its source template,
not only the generated `portal/index.html`, so rebuilding another server produces
the same interface. The Web UI already contains English translations; the
deployment launcher initializes `preferred_language: en` for new instances.

Existing volumes are deliberately preserved by initialization. Before updating
them, back up their `data/config/config.yaml` files privately. Set English using
the Web UI language setting, or call the existing authenticated WebSocket method
`locale.set_conf` with `{"preferred_language":"en"}` for each assigned instance.
Check `locale.get_conf` and reload the browser. This updates only the language
setting; do not replace the whole configuration or reinitialize user data.

For an update containing frontend translation changes, rebuild the image from
the pulled commit, regenerate compose and the portal with `provision.py`, and
recreate the containers using the new immutable image ID. Keep the original
credentials and volumes. Verify ten English UIs, their model configuration,
authentication isolation and the Live Voice start/stop controls. Existing user
messages, project files and model-generated responses are not translated by a UI
language change. Speech/Agent behavior and physical acceptance are separate.

## Maintenance and recovery

- Runtime authorizations initially expire after 30 days. Before the recorded
  `auth_expires_at`, deliberately renew that timestamp in each private runtime
  JSON and recreate the corresponding container. Preserve its token, instance
  and hostname. An expired authorization fails startup closed. Regenerating the
  compose file does not silently extend authorization.
- Keep Speech keys server-side. Rotate both the root Speech input and the ten
  private runtime JSON copies, preserve file ownership/modes, then recreate
  containers. Changing only the input does not replace existing runtime files.
- Inspect `docker compose -f /srv/jiuwen-livevoice/compose.json ps`, container logs
  and each `data/logs/live_voice_container_contract.json`. The contract records
  source, asset hashes and the real Speech preflight without credentials/audio.
- Stop the compose service before a consistent backup of `instances`, `private`,
  `auth`, compose/Nginx configuration and certificate material. Treat backups as
  private because user API settings and task history are included. Start it again
  after the backup; test restoration into a separate protected environment.
- For an image rollback, retain the existing volumes and regenerate compose with
  the previous immutable image ID, then recreate affected containers. Verify
  database compatibility first; a backup is necessary before schema migrations.
  Do not use `down -v`, delete instance directories, or rerun initialization over
  unidentified user data. Incomplete first initialization deliberately requires
  inspection; the launcher will not overwrite it automatically.
- Do not restart the unrelated `jiuwen@co-scribe` service or alter its Tailscale
  route. Record its HTTP and process status before and after deployment changes.

See the [deployment review and evidence](../../live-voice/reviews/TEN_USER_DEPLOYMENT_20260907.md).
