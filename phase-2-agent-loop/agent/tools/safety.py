"""Safety utilities — command blocking and output truncation."""

import re

# Commands that could cause serious harm.
#
# This is a blocklist, which means it is a speed bump and not a sandbox: it
# enumerates known-bad strings, and there is always one more phrasing it does
# not cover. Real containment restricts what a process can reach, not what its
# command looks like. Treat these patterns as a last-resort backstop.
#
# Note the care taken around the trailing separator. A naive `/\b` fails to
# match a bare trailing slash, because \b requires a word character after the
# slash — which would block `rm -rf /tmp` while allowing `rm -rf /`, exactly
# backwards. Match end-of-string, whitespace, or a glob instead.
DANGEROUS_PATTERNS = [
    r"\brm\s+(-\w+\s+)*-\w*[rf]\w*\s+/(\s|$|\*)",   # rm -rf /  and  rm -rf /*
    r"\brm\s+(-\w+\s+)*-\w*[rf]\w*\s+~(/|\s|$)",    # rm -rf ~  and  rm -rf ~/...
    r"\brm\s+(-\w+\s+)*-\w*[rf]\w*\s+\$HOME",       # rm -rf $HOME
    r"\bsudo\s+rm\b",           # sudo rm
    r"\bmkfs\b",                # format filesystem
    r"\bdd\s+if=",              # disk destroyer
    r"\bshutdown\b",            # shutdown system
    r"\breboot\b",              # reboot system
    r"\binit\s+0\b",            # halt system
    r">\s*/dev/sd",             # write to raw disk
    r"\bchmod\s+-R\s+777\s+/",  # open permissions on root
    r":\s*\(\)\s*\{.*\|.*&.*\}\s*;\s*:",  # fork bomb :(){ :|:& };:
]

MAX_OUTPUT_LENGTH = 50_000


def is_dangerous_command(command: str) -> bool:
    """Check if a command matches any dangerous pattern."""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return True
    return False


def truncate_output(output: str, max_length: int = MAX_OUTPUT_LENGTH) -> str:
    """Truncate output if it exceeds the maximum length."""
    if len(output) <= max_length:
        return output
    half = max_length // 2
    return (
        output[:half]
        + f"\n\n... [truncated {len(output) - max_length} characters] ...\n\n"
        + output[-half:]
    )
