#!/usr/bin/env python3
# Copyright (c) 2016 Matt Borgerson
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
"""
Controller for the Embrava Blynclight (BLYNCUSB30-152) USB LED indicator.
"""
from argparse import ArgumentParser
from math import pow, sin, cos, fabs, pi
from time import sleep
import sys
import usb.core
import usb.util

class BlynclightNotFound(Exception):
	pass

class Blynclight(object):
	BLYNCLIGHT_VENDOR  = 0x0e53
	BLYNCLIGHT_PRODUCT = 0x2516

	def __init__(self):
		"""Constructor"""
		self.dev = usb.core.find(idVendor=self.BLYNCLIGHT_VENDOR,
		                         idProduct=self.BLYNCLIGHT_PRODUCT)
		if self.dev is None:
			raise BlynclightNotFound()

		for cfg in self.dev:
			for intf in cfg:
				if self.dev.is_kernel_driver_active(intf.bInterfaceNumber):
					self.dev.detach_kernel_driver(intf.bInterfaceNumber)

		self.dev.set_configuration()

	def set_rbg(self, r, b, g):
		# Clamp RBG to [0, 255]
		r = int(max(0, min(r, 255)))
		b = int(max(0, min(b, 255)))
		g = int(max(0, min(g, 255)))
		d = (r, b, g, 0x00, 0x00, 0x00, 0xff, 0xff)
		self.dev.ctrl_transfer(0x21, 0x9, 0x0200, 0, d, 0)

def cycle(args):
	"""Cycle through red, blue, green colors"""
	bl = Blynclight()
	t = 0.0
	refresh = 0.017
	while True:
		t += args.speed*refresh
		r = int(256 * pow(sin(t        ), 8))
		b = int(256 * pow(sin(t+0.66*pi), 8))
		g = int(256 * pow(sin(t+0.33*pi), 8))
		if args.verbose: print("%d,%d,%d" % (r,b,g))
		bl.set_rbg(r, b, g)
		sleep(refresh)

def color(args):
	"""Set a specific color"""
	bl = Blynclight()
	bl.set_rbg(int(args.red), int(args.blue), int(args.green))

def pulse(args):
	"""Pulse a specific color"""
	bl = Blynclight()
	t = 0.0
	refresh = 0.017
	i = 0
	while True:
		t += args.speed*refresh
		scale = pow(sin(t),2)
		r = int(args.red * scale)
		b = int(args.blue * scale)
		g = int(args.green * scale)
		if args.verbose: print("%d,%d,%d" % (r,b,g))
		bl.set_rbg(r, b, g)
		sleep(refresh)
		if t > pi:
			t = 0
			i += 1
		if args.iterations > 0 and i >= args.iterations:
			return

def main():
	parser = ArgumentParser()
	parser.add_argument('--verbose', action='store_true')
	subparsers = parser.add_subparsers(title='command', dest='command')
	subparsers.required=True

	cmd_cycle = subparsers.add_parser('cycle', help=cycle.__doc__)
	cmd_cycle.add_argument('--speed', type=float)
	cmd_cycle.set_defaults(func=cycle, speed=0.5)

	cmd_color = subparsers.add_parser('color', help=color.__doc__)
	cmd_color.add_argument('red', type=int, help='Red intensity [0,255]')
	cmd_color.add_argument('blue', type=int, help='Blue intensity [0,255]')
	cmd_color.add_argument('green', type=int, help='Green intensity [0,255]')
	cmd_color.set_defaults(func=color)

	cmd_pulse = subparsers.add_parser('pulse', help=pulse.__doc__)
	cmd_pulse.add_argument('--speed', type=float)
	cmd_pulse.add_argument('--iterations', type=int, help='Number of pulses')
	cmd_pulse.add_argument('red', type=int, help='Red intensity [0,255]')
	cmd_pulse.add_argument('blue', type=int, help='Blue intensity [0,255]')
	cmd_pulse.add_argument('green', type=int, help='Green intensity [0,255]')
	cmd_pulse.set_defaults(func=pulse, speed=4, iterations=3)

	args = parser.parse_args()

	try:
		args.func(args)
	except BlynclightNotFound as e:
		sys.stderr.write('Error: Could not find Blynclight. Is it plugged in?\n')
		sys.exit(1)

if __name__ == '__main__':
	main()
