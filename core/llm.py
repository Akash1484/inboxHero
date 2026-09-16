"""
One function, generate(), stands between the rest of the system and any
language model. By default (MODEL_PROVIDER=template, the shipped setting)
nothing here calls out to a model at all -- drafts are built by filling in
a plain-language template with facts the rest of the pipeline has already
grounded and verified (see core/drafting.py). That was a deliberate choice,
not a missing feature: this inbox's replies are short, factual acknowledgments
where the correct wording is mechanical once you know which message you're
grounding against, so a template is both cheaper and more auditable than a
model call -- every word in a draft can be traced to a field on a message
object, not to a model's judgment call. See Final Report Q4 for the
trade-off discussion.

If a real model would help (longer freeform replies, paraphrasing a long
thread), set MODEL_PROVIDER and MODEL_API_KEY in the environment (see
config.py / .env.example) and extend the branch below -- the rest of the
codebase only ever calls generate(), so nothing else needs to change.
"""
import time

import config


class RateLimitBackoff:
    """Small helper for the free-tier model path: sleep a bit between calls
    and retry once on a 429-shaped error. Not exercised by the template
    path, but kept here so switching providers doesn't require re-adding it."""

    def __init__(self, min_interval_seconds=4):
        self.min_interval = min_interval_seconds
        self._last_call = 0.0

    def wait(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.time()


_backoff = RateLimitBackoff()


def generate(prompt, system=None, max_retries=1):
    """Returns generated text. Template provider fills prompt straight
    through (callers pass fully-formed text, not instructions) so this is
    intentionally a pass-through -- see drafting.py for how drafts are
    actually composed."""
    if config.MODEL_PROVIDER == "template":
        return prompt

    # Real-provider path (not used by the default demo). Left minimal and
    # provider-agnostic on purpose -- fill in the matching SDK call for
    # whichever MODEL_PROVIDER is configured.
    _backoff.wait()
    for attempt in range(max_retries + 1):
        try:
            raise NotImplementedError(
                f"MODEL_PROVIDER={config.MODEL_PROVIDER} is set, but no SDK "
                "call is wired up for it. Add one here, or set "
                "MODEL_PROVIDER=template to use the deterministic drafter."
            )
        except NotImplementedError:
            if attempt >= max_retries:
                raise
            _backoff.wait()
