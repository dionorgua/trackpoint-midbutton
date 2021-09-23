#!/usr/bin/env python3

from collections import namedtuple
import fcntl
import glob
import os
import select
import sys
import time
import libevdev

TRACKPOINT_NAME = [
    # HP Elitebook 850 G7 has three devices with same name. So additional magic is needed
    "SYNA30B4:00 06CB:CE09",
]

# To propertly detect middle button press we'll postpone left/right click to check if second button is pressed
# With large timeout value it's easier to trigger middle button, but regular click is more sluggish
# Since right button is not used in gestures, we can have larger timeout for it

BtnProps = namedtuple('BtnProps', 'code delay max_offset')

BTN_SETTINGS = {
    libevdev.EV_KEY.BTN_LEFT: BtnProps(code=libevdev.EV_KEY.BTN_LEFT, delay=100, max_offset=5),
    libevdev.EV_KEY.BTN_RIGHT: BtnProps(code=libevdev.EV_KEY.BTN_RIGHT, delay=200, max_offset=10)
}

IS_DEBUG = "DEBUG" in os.environ


def log_dbg(*args, **kwargs):
    if IS_DEBUG:
        print("DBG:", *args, **kwargs)


def log_msg(*args, **kwargs):
    print("MSG:", *args, **kwargs)


def detect_input_device():
    for event_file in glob.iglob("/dev/input/event*", recursive=False):
        with open(event_file, 'rb') as fd:
            dev = libevdev.Device(fd)
            if dev.name not in TRACKPOINT_NAME:
                continue
            supported = dev.evbits
            if libevdev.EV_ABS in supported:
                # can report absolute position so most likely touchpad
                continue
            keys = supported.get(libevdev.EV_KEY)
            if not keys:
                # has no buttons?
                continue
            # HP Elitebook 850 G7 trackpoint reports three buttons but actually has only two
            if libevdev.EV_KEY.BTN_MIDDLE in keys:
                return event_file


def main(args):
    input_device = detect_input_device()
    if not input_device:
        log_msg("Can't detect input device", file=sys.stderr)
        sys.exit(1)

    log_msg('Using {} as input device'.format(input_device))

    input_fd = open(input_device, 'rb')
    fcntl.fcntl(input_fd, fcntl.F_SETFL, os.O_NONBLOCK)  # optional
    input_dev = libevdev.Device(input_fd)
    input_dev.grab()

    input_dev.name = input_dev.name + " trackpoint"
    output_dev = input_dev.create_uinput_device()
    log_msg('Output device: {}'.format(output_dev.devnode))

    input_poll = select.poll()
    input_poll.register(input_fd, select.POLLRDNORM)

    class State(object):
        def __init__(self):
            self.queued_event = None
            self.settings = None
            self.emulating = False
            self.offset_x = 0
            self.offset_y = 0

        def clear(self):
            log_dbg("CLEAR")
            self.queued_event = None
            self.settings = None
            self.offset_x = 0
            self.offset_y = 0

        def timeout(self):
            if self.settings is not None:
                return self.settings.delay
            return None

        def send_queued(self):
            log_dbg("SEND: ", self.queued_event)
            output_dev.send_events([self.queued_event, libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT, 0)])
            if state.offset_x != 0 or state.offset_y != 0:
                events = []
                if state.offset_x != 0:
                    events.append(libevdev.InputEvent(libevdev.EV_REL.REL_X, state.offset_x))
                if state.offset_y != 0:
                    events.append(libevdev.InputEvent(libevdev.EV_REL.REL_Y, state.offset_y))
                events.append(libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT, 0))
                log_dbg("SEND_MOVE: ", events)
                output_dev.send_events(events)
            state.offset_x = 0
            state.offset_y = 0
            self.queued_event = None

        def send_queued_and_clear(self):
            self.send_queued()
            self.clear()

    state = State()

    while True:
        log_dbg("WAIT: ", state.timeout())
        poll_res = input_poll.poll(state.timeout())
        log_dbg("Loop: ", poll_res)

        if len(poll_res) == 0:
            log_dbg("Timeout")
            if state.queued_event is not None:
                state.send_queued_and_clear()
            continue

        for e in input_dev.events():
            if e.type == libevdev.EV_SYN:
                if state.queued_event:
                    # Skip SYN_REPORT if we've postponed event
                    continue
            if e.type == libevdev.EV_REL:
                if state.queued_event is not None:
                    if e.code == libevdev.EV_REL.REL_X:
                        state.offset_x += e.value
                    elif e.code == libevdev.EV_REL.REL_Y:
                        state.offset_y += e.value
                    if abs(state.offset_x) + abs(state.offset_y) > state.settings.max_offset:
                        state.send_queued_and_clear()
            if e.type == libevdev.EV_KEY:
                if e.value:
                    # Down
                    if state.queued_event is None:
                        # Initial down
                        state.queued_event = e
                        state.settings = BTN_SETTINGS[e.code]
                        log_dbg("Initial DOWN: ", e, state.settings)
                        continue
                    else:
                        log_dbg("Additional DOWN:", e)
                        if not state.emulating:
                            log_dbg("MIDDLE!")
                            state.emulating = True
                            qe = state.queued_event
                            state.queued_event = libevdev.InputEvent(libevdev.EV_KEY.BTN_MIDDLE, qe.value, qe.sec,
                                                                     qe.usec)
                            state.send_queued()
                            # eat original event
                            continue
                else:
                    # Up
                    if state.emulating:
                        log_dbg("UP MIDDLE")
                        state.emulating = False
                        state.queued_event = libevdev.InputEvent(libevdev.EV_KEY.BTN_MIDDLE, e.value, e.sec, e.usec)
                        state.send_queued()
                        continue
                    elif state.queued_event is not None:
                        log_dbg("UP:", e)
                        state.send_queued_and_clear()

            log_dbg("SEND: ", e)
            output_dev.send_events([e])


if __name__ == "__main__":
    main(sys.argv)
