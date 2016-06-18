Blynclight
==========

Open-source control software for the [Embrava
Blynclight](http://www.embrava.com/products/blync-light?variant=328886579) IM
status indicator.

Getting Started
---------------
Install dependencies:
    
    $ sudo apt-get install libusb-dev

Clone the repo:

    $ git clone https://github.com/mborgerson/blynclight.git
    $ cd blynclight

Create a virtual environment:

    $ mkdir env
    $ virtualenv -p python3 env
    $ source env/bin/activate

Install requirements:

    $ pip install -r requirements.txt

Run:

    $ python src/blynclight.py cycle

Commands
--------
* `cycle`: Cycle through red, blue, green colors
* `color`: Set a specific color
* `pulse`: Pulse a specific color

Run with `--help` for more details.
