import os
import signal
import utilities
import psutil

if __name__ == '__main__':
    line = utilities.get_last_line()
    utilities.kill_last_process(line)
