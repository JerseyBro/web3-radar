class SkipTest(Exception):
    pass

def skip(reason: str):
    raise SkipTest(reason)

def module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False
