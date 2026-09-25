"""Internal POSIX resource-limit launcher; never imports repository modules."""

import os
import sys


def main() -> None:
    if sys.platform != "linux":
        raise RuntimeError("resource sandbox requires Linux")
    import resource

    memory, cpu, output, processes = map(int, sys.argv[1:5])
    for key, limit in (
        (resource.RLIMIT_AS, memory * 1024 * 1024),
        (resource.RLIMIT_CPU, cpu),
        (resource.RLIMIT_FSIZE, output),
        (resource.RLIMIT_NPROC, processes),
        (resource.RLIMIT_NOFILE, 64),
        (resource.RLIMIT_CORE, 0),
    ):
        resource.setrlimit(key, (limit, limit))
    os.execv(sys.argv[5], sys.argv[5:])


if __name__ == "__main__":
    main()
