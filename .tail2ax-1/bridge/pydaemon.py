'''
    This module is used to fork the current process into a daemon.
    Almost none of this is necessary (or advisable) if your daemon
    is being started by inetd. In that case, stdin, stdout and stderr are
    all set up for you to refer to the network connection, and the fork()s
    and session manipulation should not be done (to avoid confusing inetd).
    Only the chdir() and umask() steps remain as useful.
    References:
        UNIX Programming FAQ
            1.7 How do I get my program to act like a daemon?
                http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
        Advanced Programming in the Unix Environment
            W. Richard Stevens, 1992, Addison-Wesley, ISBN 0-201-56317-7.

    History:
      2001/07/10 by Jurgen Hermann
      2002/08/28 by Noah Spurrier
      2003/02/24 by Clark Evans

      http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/66012
'''
import sys
import os
import time
from signal import SIGTERM
import posix

HOME = '/'


def deamonize(stdout='/dev/null', stderr=None, stdin='/dev/null',
              pidfile=None, startmsg='started with pid %s'):
    '''
        This forks the current process into a daemon.
        The stdin, stdout, and stderr arguments are file names that
        will be opened and be used to replace the standard file descriptors
        in sys.stdin, sys.stdout, and sys.stderr.
        These arguments are optional and default to /dev/null.
        Note that stderr is opened unbuffered, so
        if it shares a file with stdout then interleaved output
        may not appear in the order that you expect.
    '''
    # Do first fork.
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)  # Exit first parent.
    except OSError as e:
        sys.stderr.write("fork #1 failed: (%d) %s\n" % (e.errno, e.strerror))
        sys.exit(1)

    # Decouple from parent environment.
    os.chdir(HOME)
    os.umask(0)
    os.setsid()

    # Do second fork.
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)  # Exit second parent.
    except OSError as e:
        sys.stderr.write("fork #2 failed: (%d) %s\n" % (e.errno, e.strerror))
        sys.exit(1)

    # Open file descriptors and print start message
    if not stderr:
        stderr = stdout
    # parche para poder leer de una fifo
    # si = open(stdin, 'r')
    si = posix.open(stdin, posix.O_RDONLY | posix.O_NONBLOCK)
    so = open(stdout, 'a+')
    se = open(stderr, 'a+b', 0)
    pid = str(os.getpid())
    sys.stderr.write("\n%s\n" % startmsg % pid)
    sys.stderr.flush()
    if pidfile:
        open(pidfile, 'w+').write("%s\n" % pid)

    # Redirect standard file descriptors.
    # parche para poder leer de una fifo
    # os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(si, sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())


def startstop(stdout='/dev/null', stderr=None, stdin='/dev/null',
              pidfile='pid.txt', startmsg='started with pid %s',
              ):
    if len(sys.argv) != 2:
        print("usage: %s start|stop|restart" % sys.argv[0])
        sys.exit(2)

    action = sys.argv[1]
    pid = None
    try:
        with open(pidfile, 'r') as pf:
            pid = int(pf.read().strip())
    except (IOError, ValueError):
        pass  # PID file doesn't exist or is invalid

    if action == 'start':
        if pid:
            sys.stderr.write(f"Start aborted, pid file '{pidfile}' exists with pid {pid}.\n")
            sys.exit(1)
        deamonize(stdout, stderr, stdin, pidfile, startmsg)
        return

    elif action == 'stop':
        if not pid:
            sys.stderr.write(f"Could not stop, pid file '{pidfile}' missing.\n")
            sys.exit(1)
        try:
            os.kill(pid, SIGTERM)
            print(f"Sent stop signal to daemon with pid {pid}.")
            time.sleep(1) # Give it a moment to die
            os.remove(pidfile)
        except OSError as err:
            if "No such process" in str(err):
                print(f"Process {pid} not found. Removing stale pid file.")
                try:
                    os.remove(pidfile)
                except FileNotFoundError:
                    pass
            else:
                sys.stderr.write(f"Error killing process {pid}: {err}\n")
                sys.exit(1)
        return

    elif action == 'restart':
        if pid:
            print(f"Stopping daemon (pid: {pid}) for restart...")
            try:
                os.kill(pid, SIGTERM)
                time.sleep(2)  # Wait for the process to terminate
            except OSError as err:
                sys.stderr.write(f"Warning: could not kill process {pid} during restart: {err}\n")
        print("Starting daemon...")
        deamonize(stdout, stderr, stdin, pidfile, startmsg)
        return

    else:
        print(f"Unknown command: '{action}'")
        print(f"usage: {sys.argv[0]} start|stop|restart")
        sys.exit(2)


def test():
    '''
        This is an example main function run by the daemon.
        This prints a count and timestamp once per second.
    '''
    sys.stdout.write('Message to stdout...')
    sys.stderr.write('Message to stderr...')
    c = 0
    while 1:
        sys.stdout.write('%d: %s\n' % (c, time.ctime(time.time())))
        sys.stdout.flush()
        c = c + 1
        time.sleep(1)


if __name__ == "__main__":
    startstop(stdout='/tmp/deamonize.log',
              pidfile='/tmp/deamonize.pid')
    test()
