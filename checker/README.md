`checker` is an application for periodically running invariants
and alerting based on violations of those invariants. At a high level
integrating into it is simple:

```
@register_checker
def no_bad_things_are_happening_checker():
  if bad_things_are_happening:
    yield CheckerFailure(text="Oh no! Bad things are happening!")
```

These checkers should be declared in `{app}.checkers`, for purposes
of autodiscovery.

At some point, I'd like to open-source this app (I don't think anything similar exists). This is why I've sequestered Buttondown-specific logic
in `checker/reactions`; you can imagine that these would be declared in settings or something similar,
but it's not worth the effort at the moment to add all of that abstraction.
