#!/usr/bin/env python3
#
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
Controller for the Embrava Blynclight (BLYNCUSB30-152) USB LED indicator
"""
from argparse import ArgumentParser
from math import pi, pow, sin, cos
from time import sleep
import os
import sys
import usb.core
import multiprocessing
import threading
import tkinter
import queue

if sys.platform == "win32":
	# Add script path to PATH environment variable so libusb DLL can be found
	os.environ['PATH'] = os.path.dirname(__file__) + ';' + os.environ['PATH']

#-------------------------------------------------------------------------------
# Effect Helper Classes
#-------------------------------------------------------------------------------

class Color(object):
	def __init__(self, rbg=(0,0,0)):
		r, b, g = rbg
		self._r = r
		self._b = b
		self._g = g

	def __eq__(self, other):
		return (self.r == other.r) and \
		       (self.b == other.b) and \
		       (self.g == other.g)

	@property
	def r(self): return self._r
	@r.setter
	def r(self, value): self._r = value

	@property
	def b(self): return self._b
	@b.setter
	def b(self, value): self._b = value

	@property
	def g(self): return self._g
	@g.setter
	def g(self, value): self._g = value

class Effect(object):
	def __init__(self, light, step=(1.0/60), speed=1.0, start=0.0, end=1.0, color=None):
		self._light         = light
		self._step          = step
		self._speed         = speed
		self._t             = 0.0
		self._start         = start
		self._end           = end
		self._color         = color
		self._initial_color = self._color

	def setup(self):
		pass

	def render(self):
		"""Render the entire effect"""
		self._t = self._start
		self.setup()
		while True:
			self.update(self._t)
			self._light.set_color(self._color)
			self._sleep()
			if self._t >= self._end: break
			self._t = min(self._t + self._speed*self._step, self._end)

	def update(self, t):
		"""Update frame of effect"""
		pass

	def _sleep(self):
		"""Wait to update for next frame"""
		sleep(self._step)

class ConstantEffect(Effect):
	"""Set a specific color"""
	pass

class InterpolateEffect(Effect):
	"""Interpolate between previous color and next color."""

	def setup(self):
		self._initial_color = self._light.get_color()
		self._final_color = self._color

	def update(self, t):
		r = self.interpolate_cosine(self._initial_color.r, self._final_color.r, t)
		b = self.interpolate_cosine(self._initial_color.b, self._final_color.b, t)
		g = self.interpolate_cosine(self._initial_color.g, self._final_color.g, t)
		self._color = Color((r,b,g))

	def interpolate_linear(self, v1, v2, t):
		return v1 + t*(v2-v1)

	def interpolate_cosine(self, v1, v2, t):
		return self.interpolate_linear(v1, v2, 0.5-0.5*cos(t*pi))

class PulseEffect(Effect):
	"""Pulse a specific color"""

	def setup(self):
		pass

	def update(self, t):
		scale = pow(sin(t*pi),4)
		r = int(self._initial_color.r * scale)
		b = int(self._initial_color.b * scale)
		g = int(self._initial_color.g * scale)
		self._color = Color((r,b,g))

class EffectSequence(object):
	def __init__(self, light, seq=None, speed=1.0):
		self._light = light
		self._seq   = seq or []
		self._speed = speed

	def interpolate_effect(self, e):
		# Get current color
		current_color = self._light.get_color()

		# Get color of first frame of effect
		e.setup()
		e.update(0.0)
		next_color = e._color

		# Interpolate colors if different
		if next_color != current_color:
			ie = InterpolateEffect(light=self._light, speed=self._speed, color=next_color)
			ie.render()

	def render(self):
		for e in self._seq:
			self.interpolate_effect(e)
			e.render()

#-------------------------------------------------------------------------------
# Blynclight Device Communication Class
#-------------------------------------------------------------------------------

class BlynclightNotFound(Exception):
	pass

class Blynclight(object):
	BLYNCLIGHT_VENDOR  = 0x0e53
	BLYNCLIGHT_PRODUCT = 0x2516

	def __init__(self, verbose=False):
		"""Constructor"""
		self.dev = usb.core.find(idVendor=self.BLYNCLIGHT_VENDOR,
		                         idProduct=self.BLYNCLIGHT_PRODUCT)
		if self.dev is None:
			raise BlynclightNotFound()

		if sys.platform != "win32":
			for cfg in self.dev:
				for intf in cfg:
					if self.dev.is_kernel_driver_active(intf.bInterfaceNumber):
						self.dev.detach_kernel_driver(intf.bInterfaceNumber)

		self.dev.set_configuration()
		self._color = Color()
		self._verbose = verbose

	def set_color(self, color):
		# Clamp RBG to [0, 255]
		r = int(max(0, min(color.r, 255)))
		b = int(max(0, min(color.b, 255)))
		g = int(max(0, min(color.g, 255)))
		d = (r, b, g, 0x00, 0x00, 0x00, 0xff, 0xff)
		self.dev.ctrl_transfer(0x21, 0x9, 0x0200, 0, d, 0)
		if self._verbose: print(r,b,g)
		self._color = color

	def get_color(self):
		return self._color

#-------------------------------------------------------------------------------
# Blynclight Device Simulator Communication Class
#-------------------------------------------------------------------------------

class BlynclightSimulatorIpc(threading.Thread):
	"""Thread which handles interprocess communication with the controller"""

	def __init__(self, ipc_queue, window):
		"""Constructor"""
		threading.Thread.__init__(self)
		self._ipc_queue = ipc_queue
		self._window = window

	def run(self):
		"""Processes simulator events"""

		# Wait for the window to be created
		self._window.is_ready.wait()

		# Process events sent by the controller
		while True:
			a = self._ipc_queue.get()
			if a['action'] == 'update':
				self._window.set_rbg(*a['color'])
			elif a['action'] == 'quit':
				self._window.stop()
				return
			else:
				raise ValueError('Unknown event')

class BlynclightSimulatorWindow(object):
	"""Simulator Window class"""

	def __init__(self):
		"""Constructor"""
		self._queue = queue.Queue()
		self._root = tkinter.Tk()
		self._root.title('Blynclight Simulator')
		self._root.geometry('250x250')
		self._root.bind('<<UpdateColor>>', self._update_color)
		self._root.bind('<<Quit>>', self._quit)
		self.is_ready = threading.Event()

	def start(self):
		# Display the window and begin the Tk event loop handler, then notify
		# the IPC object that the window is ready to be used
		self._root.after(0, self.is_ready.set)
		self._root.mainloop()

	def stop(self):
		# Generate the Quit event to start shutting down the window/event loop
		self._root.event_generate('<<Quit>>', when='tail')

	def set_rbg(self, r, b, g):
		# Create an event to set the background color of the window
		self._queue.put((r, b, g))
		self._root.event_generate('<<UpdateColor>>', when='tail')

	def _update_color(self, event):
		# Handle the UpdateColor event, updating the window BG color
		r, b, g = self._queue.get()
		self._root.configure(background='#%02x%02x%02x' % (r,g,b))

	def _quit(self, event):
		# Close the window and exit the event loop
		self._root.quit()

class BlynclightSimulator(object):
	"""Main simulator class"""

	def __init__(self, verbose=False):
		"""Constructor"""
		self._queue = multiprocessing.Queue()
		self._subproc = multiprocessing.Process(target=self._proc,
		                                        args=(self._queue,))
		self._color = Color()
		self._verbose = verbose

	def start(self):
		"""Spawn the simulator process"""
		self._subproc.start()

	def stop(self):
		"""Shutdown the simulator"""
		self._queue.put({'action': 'quit'})

	def set_color(self, color):
		# Clamp RBG to [0, 255]
		r = int(max(0, min(color.r, 255)))
		b = int(max(0, min(color.b, 255)))
		g = int(max(0, min(color.g, 255)))
		self._queue.put({'action': 'update', 'color': (r, b, g)})
		self._color = color
		if self._verbose: print(r,b,g)


	def get_color(self):
		return self._color

	def _proc(self, q):
		"""Method which is run in a new process"""
		try:
			window = BlynclightSimulatorWindow()
			ipc = BlynclightSimulatorIpc(q, window)
			ipc.start()
			window.start()
		except KeyboardInterrupt:
			# Handled by the parent process
			pass

#-------------------------------------------------------------------------------
# Application
#-------------------------------------------------------------------------------

def cycle(bl, args):
	"""Cycle through red, blue, green colors"""
	eseq = [ConstantEffect(light=bl, end=0.0, color=Color((255,0,0))),
	        ConstantEffect(light=bl, end=0.0, color=Color((0,255,0))),
	        ConstantEffect(light=bl, end=0.0, color=Color((0,0,255)))]
	seq = EffectSequence(bl, eseq, speed=args.speed)
	while True: seq.render()

def color(bl, args):
	"""Set a specific color"""
	color = Color((args.red, args.blue, args.green))
	e = ConstantEffect(light=bl, end=0.0, color=color)
	e.render()

def pulse(bl, args):
	"""Pulse a specific color"""
	color = Color((args.red, args.blue, args.green))
	e = PulseEffect(light=bl, speed=args.speed, color=color)
	for i in range(args.iterations): e.render()

def main():
	parser = ArgumentParser(description=__doc__)
	parser.add_argument('--verbose', action='store_true')
	parser.add_argument('--simulate', action='store_true')
	subparsers = parser.add_subparsers(title='command', dest='command')
	subparsers.required = True

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
	cmd_pulse.set_defaults(func=pulse, speed=1, iterations=3)

	args = parser.parse_args()

	if args.simulate:
		bl = BlynclightSimulator(verbose=args.verbose)
		try:
			bl.start()
			args.func(bl, args)
			bl.stop()
		except KeyboardInterrupt:
			bl.stop()
	else:
		try:
			bl = Blynclight(verbose=args.verbose)
			args.func(bl, args)
		except BlynclightNotFound as e:
			sys.stderr.write('Error: Could not find Blynclight. Is it plugged in?\n')
			sys.exit(1)
		except KeyboardInterrupt:
			pass

if __name__ == '__main__':
	main()
