trackpoint-midbutton
=======

Small utility that emulates middle mouse button on laptops such as HP Elitebook 850 G7.

Why
===

HP has trackpoint on at least Elitebook series, and it's mostly ok (matches Thinkpad experience), but with just two
physical mouse buttons. And even worse, it reports that trackpoint has three buttons, so built-in emulation of
`libinput` is not turned on by default.

Unfortunately `libinput` feature to emulate third mouse button is not very useful for trackpoints because it's much
harder to press both touchpad buttons simultaneously (using just one finger). And there is no way configure it's
behavior.

So the idea is to emulate MIDDLE button by pressing LEFT and RIGHT buttons at the same time.
Some trackpoint-specific things should improve user experience:
* It should be possible to press both buttons together using single finger
* Almost not mouse move while pressing

The goal is to have 'middle button paste' and MIDDLE button + trackpoint to scroll gestures working.

How it works
============

Basically it's just python script that creates userspace input device (uinput) opens real trackpoint device exclusively
and forwards most of trackpoint events. Except clicks:

* if first mouse button is pressed, event is queued. All further moves are also queued
* if first mouse button is released, both DOWN and UP events are forwarded
* if mouse is moved with first button pressed, DOWN and MOVE events are forwarded
* if second button is pressed while first button is DOWN, middle button DOWN is emulated

Since left and right mouse buttons are not used same way, (usually there is no right button DRAG events),
different timeout values are used. So it's easier to get MIDDLE button by pressing right mouse button first.

Usage
=====

For EliteBook 850 G7 just run script as root. For other laptops `detect_input_device` should be hacked.

TODO
====

swap left/right button, config file, systemd unit, etc
