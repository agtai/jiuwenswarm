"""
Démo live des composants E1 (SDK) — branche PR #2540, racine du repo :
    python demo_e1_sdk.py
"""

import asyncio
import inspect
import time

SDK = "jiuwenswarm.gateway.channel_manager.sdk"

def imp(module, *names):
    mod = __import__(f"{SDK}.{module}", fromlist=list(names))
    return [getattr(mod, n) for n in names]


def title(t):
    print(f"\n{'='*60}\n  {t}\n{'='*60}")


# 1) PR #2288/#2393 — ChannelCapabilities
def demo_capabilities():
    title("1. ChannelCapabilities — feuille déclarative immuable")
    (ChannelCapabilities,) = imp("capabilities", "ChannelCapabilities")

    print("Feuille par défaut (conservatrice) :", ChannelCapabilities())
    rich = ChannelCapabilities(buttons=True, streaming=True)
    print("Canal riche :", rich)
    try:
        rich.buttons = False
        print("!! PROBLÈME : la mutation a été acceptée")
    except Exception as e:
        print(f"Mutation refusée comme prévu → {type(e).__name__}")


# 2) PR #2536 — InteractiveCard
def demo_card():
    title("2. InteractiveCard — dégradation gracieuse aller/retour")
    Card, Button = imp("cards", "InteractiveCard", "Button")

    card = Card(
        text="Deploy v2.3?",
        buttons=(Button(label="Approve", action="approve"),
                 Button(label="Deny", action="deny")),
    )
    print("Canal SANS boutons →", card.degrade_to_text())
    print('Réponse "1" →', card.action_for_reply("1"))
    print('Réponse "2" →', card.action_for_reply("2"))


# 3) PR #2536 — RichText (bonus)
def demo_rich_text():
    title("3. RichText — format pivot, rendu par capacité")
    RichText, Span, SpanStyle = imp("rich_text", "RichText", "Span", "SpanStyle")

    rt = RichText(spans=(
        Span("Déploiement ", SpanStyle.PLAIN),
        Span("réussi", SpanStyle.BOLD if hasattr(SpanStyle, "BOLD") else SpanStyle.PLAIN),
    ))
    print("render_plain    →", rt.render_plain() if hasattr(rt, "render_plain") else "(module-level)")
    print("render_markdown →", rt.render_markdown() if hasattr(rt, "render_markdown") else "(module-level)")


# 4) PR #2540 — TokenBucketRateLimiter
async def demo_rate_limiter():
    title("4. TokenBucketRateLimiter — rafale de 10, débit lissé")
    (TokenBucketRateLimiter,) = imp("reliability", "TokenBucketRateLimiter")

    limiter = TokenBucketRateLimiter(capacity=5, rate=5)
    t0 = time.perf_counter()
    for i in range(10):
        await limiter.acquire()
        print(f"  msg {i+1:2d} envoyé à t = {time.perf_counter()-t0:5.2f}s")
    print("→ burst de 5, puis lissage à 5 msg/s")


# 5) PR #2515 — StreamingResponder (les DEUX branches de capacité)
async def demo_streaming():
    title("5. StreamingResponder — capability-aware")
    (StreamingResponder,) = imp("streaming", "StreamingResponder")
    text = "La négociation de capacités est le mécanisme central du SDK .".split()

    for flag in (True, False):
        sent, edits = [], []

        async def fake_send(t):
            sent.append(t); print(f"  [send] {t!r}"); return "msg-001"

        async def fake_edit(mid, t):
            edits.append(t); print(f"  [edit {len(edits):2d}] {t!r}")

        print(f"\n--- supports_streaming={flag} ---")
        r = StreamingResponder(send=fake_send, edit=fake_edit, supports_streaming=flag)
        for tok in text:
            await r.append(tok + " ")
            await asyncio.sleep(0.03)
        await r.finalize()
        print(f"→ {len(text)} tokens · {len(sent)} send · {len(edits)} edits")


# 6) PR #2540 — SessionIdPolicy + RetryPolicy
def demo_session_and_retry():
    title("6. SessionIdPolicy & RetryPolicy (backoff)")
    SessionIdPolicy, RetryPolicy = imp("reliability", "SessionIdPolicy", "RetryPolicy")

    policy = SessionIdPolicy()
    try:
        sid = policy.build("web", "chaimae")
    except TypeError:
        print("signature de build :", inspect.signature(policy.build))
        raise
    print("session_id généré :", sid)

    retry = RetryPolicy(base_delay=0.5, max_delay=8)
    delays = [retry.delay_for(a) for a in range(1, 7)]
    print("délais de retry :", [f"{d:.1f}s" for d in delays], "→ plafonné à max_delay")


if __name__ == "__main__":
    demo_capabilities()
    demo_card()
    demo_rich_text()
    asyncio.run(demo_rate_limiter())
    asyncio.run(demo_streaming())
    demo_session_and_retry()
    print("\n✔ Démo E1 terminée — tous les composants exercés.")