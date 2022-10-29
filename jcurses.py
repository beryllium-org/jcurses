from sys import stdout, stdin
from supervisor import runtime
from jcurses_data import char_map
from time import sleep

ESCK = "\033["


class jcurses:
    def __init__(self):
        """
        trigger_dict : What to do when what key along with other intructions.

        trigger_dict values:
            "*any value from char_map*": exit the program with the value as an exit code.
                For instance: "enter": 1. The program will exit when enter is pressed with exit code 1.
            "rest": what to do with the rest of keys, type string, can be "stack" / "ignore"
            "rest_a": allowed keys to be parsed with "rest", not neccessary if rest is set to ignore.
                Valid values: "all" / "lettersnumbers" / "numbers" / "letters" / "common".
            "echo": Can be "all" / "common" / "none".
        """
        self.enabled = False  # jcurses has init'ed
        self.softquit = False  # internal bool to signal exiting
        self.reset = False  # set to true to hard reset jcurses
        # handy variable to make multi-action keys easily parsable
        self.text_stepping = 0
        self.ctx_dict = {
            "top_left": [1, 1],
            "bottom_left": [255, 255],
            "line_len": 255,
        }
        self.trigger_dict = None
        self.dmtex_suppress = False
        self.buf = [0, ""]
        self.focus = 0
        self.stdin = None  # a register for when we need to clear stdin
        self.spacerem = -1

    def update_rem(self):
        self.spacerem = self.ctx_dict["line_len"] - self.detect_pos()[1]

    def clear_buffer(self):
        self.stdin = None
        n = runtime.serial_bytes_available
        if n > 0:
            void = stdin.read(n)
            del void

    def anykey(self, msg=None):
        """
        Press any key to continue, returns key
        Optionally specify message
        """
        ret = None
        n = None
        if msg is not None:
            stdout.write(msg)
        del msg
        while True:
            sleep(0.5)
            n = runtime.serial_bytes_available
            if n > 0:
                ret = stdin.read(n)
                stdout.write("\n")
                break
        del n
        return ret

    def backspace(self, n=1):
        """
        Arguably most used key
        """
        for i in range(n):
            if len(self.buf[1]) - self.focus > 0:
                if self.focus == 0:
                    self.buf[1] = self.buf[1][:-1]
                    stdout.write("\010 \010")
                    self.spacerem += 1
                else:
                    self.spacerem += 1
                    stdout.write("\010")
                    insertion_pos = len(self.buf[1]) - self.focus - 1
                    self.buf[
                        1
                    ] = f"{self.buf[1][:insertion_pos]}{self.buf[1][insertion_pos + 1 :]}"  # backend
                    stdout.write(
                        f"{self.buf[1][insertion_pos:]} {ESCK}{str(len(self.buf[1][insertion_pos:]) + 1)}D"
                    )  # frontend
                    del insertion_pos
            del i

    def home(self):
        """
        Go to start of buf
        """
        lb = len(self.buf[1])
        df = lb - self.focus
        if df > 0:
            self.focus = lb
        stdout.write("\010" * df)
        del lb, df

    def end(self):
        """
        Go to end of buf
        """
        stdout.write(f"{ESCK}1C" * self.focus)
        self.focus = 0

    def overflow_check(self):
        if self.spacerem is -1:
            self.update_rem()
        return False if self.spacerem > 0 else True

    def delete(self, n=1):
        """
        Key delete. Like, yea, the del you have on your keyboard under insert
        """
        for i in range(n):
            if len(self.buf[1]) > 0 and self.focus > 0:
                if self.focus == len(self.buf[1]):
                    self.buf[1] = self.buf[1][1:]
                    stdout.write(f"{self.buf[1]} " + "\010" * self.focus)
                    self.spacerem += 1
                    self.focus -= 1
                else:
                    insertion_pos = len(self.buf[1]) - self.focus
                    self.buf[
                        1
                    ] = f"{self.buf[1][:insertion_pos]}{self.buf[1][insertion_pos + 1 :]}"  # backend
                    stdout.write(
                        f"{self.buf[1][insertion_pos:]} {ESCK}{str(len(self.buf[1][insertion_pos:]) + 1)}D"
                    )  # frontend
                    self.spacerem += 1
                    self.focus -= 1
                    del insertion_pos
            del i

    def clear(self):
        """
        Clear the whole screen & goto top
        """
        stdout.write(f"{ESCK}2J")
        stdout.write(f"{ESCK}H")

    def clear_line(self):
        """
        Clear the current line
        """
        stdout.write(f"{ESCK}2K")
        stdout.write(f"{ESCK}500D")

    def start(self):
        """
        Start the Jcurses system.
        """
        if self.enabled:
            self.stop()
        self.enabled = True
        self.dmtex_suppress = True
        # self.clear()

    def stop(self):
        """
        Stop the Jcurses system & reset to the default state.
        """
        self.clear(self)
        self.dmtex_suppress = False
        self.enabled = False
        self.softquit = False
        self.reset = False
        self.text_stepping = 0
        self.ctx_dict = {"zero": [1, 1]}
        self.trigger_dict = None
        self.dmtex_suppress = False

    def detect_size(self):
        """
        detect terminal size, returns [rows, collumns]
        """
        d = True
        res = None
        while d:
            try:
                strr = ""  # cannot be None

                # clearing stdin in case of fast pasting
                self.rem_gib()

                tries = 0
                while True:
                    if tries % 20:
                        print(
                            "Reading terminal size.\nIf you are seeing this message, press Ctrl+C"
                        )
                for i in range(3):
                    self.get_hw(i)
                    del i
                try:
                    while not strr.endswith("R"):  # this is an actual loop
                        strr += self.get_hw(3)
                except KeyboardInterrupt:
                    # uh oh, user is late
                    strr = ""
                    for i in range(3):
                        self.get_hw(i)
                        del i
                    while not strr.endswith("R"):
                        strr += self.get_hw(3)

                strr = strr[2:-1]  # this is critical as find will break with <esc>.
                res = [int(strr[: strr.find(";")]), int(strr[strr.find(";") + 1 :])]
                # Let's also update the move bookmarks.
                self.ctx_dict["bottom_left"] = [res[0], 1]
                self.ctx_dict["line_len"] = res[1]
                self.spacerem = res[1] - self.detect_pos()[1]
                del strr
                d = False
            except ValueError:
                pass
        del d
        return res

    def detect_pos(self):
        """
        detect cursor position, returns [rows, collumns]
        """
        d = True
        res = None
        while d:
            try:
                strr = ""

                # clearing stdin in case of fast pasting
                self.rem_gib()

                self.get_hw(1)  # we need cleared stdin for this
                try:
                    while not strr.endswith("R"):
                        strr += self.get_hw(3)
                except KeyboardInterrupt:
                    # uh oh, user is late
                    strr = ""
                    self.get_hw(1)
                    while not strr.endswith("R"):
                        strr += self.get_hw(3)

                strr = strr[2:-1]  # this is critical as find will break with <esc>.
                res = [int(strr[: strr.find(";")]), int(strr[strr.find(";") + 1 :])]
                del strr
                d = False
            except ValueError:
                pass
        del d
        return res

    def rem_gib(self):
        """
        remove gibberrish from stdin when we need to read ansi escape codes
        """

        d = True  # done
        got = False  # we got at least a few

        while d:
            n = runtime.serial_bytes_available
            if n > 0:
                got = True
                if self.stdin is None:
                    self.stdin = stdin.read(n)
                else:
                    self.stdin += stdin.read(n)
                if got:
                    sleep(0.0003)
                    """
                                'Nough time for at least a few more bytes to come, do not change
                                Without it, the captures right after, would recieve all the garbage
                                """
            else:
                d = False
        del n, d, got

    def get_hw(self, act):
        """
        Used to send and recieve, position ansi requests
        """
        if act is 0:
            # save pos & goto the end
            stdout.write(f"{ESCK}s{ESCK}500B{ESCK}500C")
        elif act is 1:
            # ask position
            stdout.write(f"{ESCK}6n")
        elif act is 2:
            # go back to original position
            stdout.write(f"{ESCK}u")
        elif act is 3:
            # get it
            return stdin.read(1)

    def training(self, opt=False):

        sleep(3)
        for i in range(0, 10):
            n = runtime.serial_bytes_available
            if n > 0:
                if not opt:
                    i = stdin.read(n)
                    for s in i:
                        print(ord(s))
                else:
                    stdout.write(str(self.register_char()))
            del i
        stdout.write("\n")

    def register_char(self):
        """
        Complete all-in-one input character registration function.
        Returns list of input.
        Usually it's a list of one item, but if too much is inputted at once
        (for example, you are pasting text)
        it will all come in one nice bundle.
        This is to improve performance & compatibility with advanced keyboard features.

        You need to loop this in a while true.
        """
        stack = []
        try:
            n = runtime.serial_bytes_available
            if n > 0 or self.stdin is not None:
                i = None
                if self.stdin is not None:
                    i = self.stdin
                    self.stdin = None
                else:
                    i = stdin.read(n)

                for s in i:
                    try:
                        charr = ord(s)
                        # Check for alt or process
                        if self.text_stepping is 0:
                            if charr != 27:
                                stack.append(char_map[charr])
                            else:
                                self.text_stepping = 1

                        # Check skipped alt
                        elif self.text_stepping is 1:
                            if charr != 91:
                                self.text_stepping = 0
                                stack.extend(["alt", char_map[charr]])
                            else:
                                self.text_stepping = 2

                        # the arrow keys and the six above
                        elif self.text_stepping is 2:
                            self.text_stepping = 3
                            stack.append(char_map[300 + charr])

                        else:
                            if charr == 126:  # garbage
                                self.text_stepping = 0
                            elif charr == 27:  # new special
                                self.text_stepping = 1
                            else:  # other
                                stack.append(char_map[charr])

                    except KeyError:
                        self.text_stepping = 0

                    del s
        except KeyboardInterrupt:
            d = True
            while d:
                try:
                    stack = ["ctrlC"]
                    d = False
                except KeyboardInterrupt:
                    pass
            del d
        return stack

    def program(self):
        """
        The main program.
        Depends on variables being already set.
        """
        self.softquit = segmented = False
        self.buf[0] = 0
        self.termline()
        while not self.softquit:
            tempstack = self.register_char()
            if tempstack:
                tempstack.reverse()
            try:
                while tempstack and not self.softquit:
                    i = tempstack.pop()
                    if i == "alt" or segmented:
                        pass
                    elif i in self.trigger_dict:
                        self.buf[0] = self.trigger_dict[i]
                        self.softquit = True
                    elif i == "bck":
                        self.backspace()
                    elif i == "del":
                        self.delete()
                    elif i == "home":
                        self.home()
                    elif i == "end":
                        self.end()
                    elif i in ["up", "ins", "down", "tab"]:
                        pass
                    elif i == "left":
                        if len(self.buf[1]) > self.focus:
                            stdout.write("\010")
                            self.focus += 1
                    elif i == "right":
                        if self.focus > 0:
                            stdout.write(ESCK + "1C")
                            self.focus -= 1
                    elif self.trigger_dict["rest"] == "stack" and (
                        self.trigger_dict["rest_a"] == "common"
                        and not (i.startswith("ctrl") or i.startswith("alt"))
                    ):  # Arknights "PatriotExtra" theme starts playing
                        if self.focus is 0:
                            if self.trigger_dict["echo"] in {"common", "all"}:
                                if not self.overflow_check():
                                    stdout.write(i)
                                    self.spacerem -= len(i)
                                    self.buf[1] += i
                                else:
                                    if self.stdin is None:
                                        self.stdin = i
                                    else:
                                        self.stdin += i
                                    while tempstack:
                                        self.stdin += tempstack.pop()
                                    self.softquit = True
                                    try:
                                        self.buf[0] = self.trigger_dict["overflow"]
                                    except KeyError:
                                        self.buf[0] = 0

                            else:
                                self.buf[1] += i
                        else:
                            insertion_pos = len(self.buf[1]) - self.focus

                            self.buf[1] = (
                                self.buf[1][:insertion_pos]
                                + i
                                + self.buf[1][insertion_pos:]
                            )

                            # frontend insertion
                            for d in self.buf[1][insertion_pos:]:
                                stdout.write(d)
                                del d

                            steps_in = len(self.buf[1][insertion_pos:])

                            for e in range(steps_in - 1):
                                stdout.write("\010")
                                del e

                            del steps_in, insertion_pos
            except KeyboardInterrupt:
                pass
            del tempstack
        del segmented
        return self.buf

    def termline(self):
        stdout.write(self.trigger_dict["prefix"] + self.buf[1])
        if self.focus > 0:
            stdout.write(f"{ESCK}{self.focus}D")
        self.update_rem()

    def move(self, ctx=None, x=0, y=0):
        """
        Move to a specified coordinate or a bookmark.
        If you specified a bookmark, you can use x & y to add an offset.
        """
        if ctx is None:
            x, y = max(1, x), max(1, y)
            stdout.write(f"{ESCK}{x};{y}H")
        else:
            thectx = self.ctx_dict[ctx]
            stdout.write(f"{ESCK}{thectx[0]};{thectx[1]}H")

            # out of bounds check for up and down
            if x + thectx[0] > 0:
                if thectx[0] > 0:
                    stdout.write(f"{ESCK}{thectx[0]}B")
                else:
                    stdout.write(f"{ESCK}{-thectx[0]}A")

            # out of bounds check for right and left
            if y + thectx[1] > 0:
                if thectx[1] > 0:
                    stdout.write(f"{ESCK}{thectx[1]}C")
                else:  # left
                    stdout.write(f"{ESCK}{-thectx[1]}D")

            del thectx

    def ctx_reg(self, namee):
        self.ctx_dict[namee] = self.detect_pos()

    def line(self, charr):
        self.clear_line()
        stdout.write(charr * self.detect_size()[1])
