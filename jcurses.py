from jcurses_data import char_map
from time import sleep, monotonic

ESCK = "\x1b["
CONV = "utf-8"


class jcurses:
    def __init__(self):
        self.enabled = False  # Jcurses has init'ed
        self.softquit = False  # Internal bool to signal exiting
        self.reset = False  # Set to true to hard reset jcurses
        self._active = None  # A check if .connected exists

        # Handy variable to make multi-action keys easily parsable
        self.text_stepping = 0
        self.ctx_dict = {
            "top_left": [1, 1],
            "bottom_left": [255, 255],
            "line_len": 255,
        }

        # Data stream to use, configure from main application
        self.console = None

        # Temporary buffers that have higher priority over the real deal.
        self.stdin_buf = None
        self.stdout_buf = None  # Can be flushed to the real one, or returned
        self.stdout_buf_b = bytes()  # Some have already been converted to bytes
        self.hold_stdout = False  # Do not flush stdout_buf

        """
        trigger_dict : What to do when what key along with other intructions.

        trigger_dict values:
            "*any value from char_map*": exit the program with the value as an exit code.
                For instance: "enter": 1. The program will exit when enter is pressed with exit code 1.
            "rest": what to do with the rest of keys, type string, can be "stack" / "ignore"
            "rest_a": allowed keys to be parsed with "rest", not neccessary if rest is set to ignore.
                Valid values: "all" / "lettersnumbers" / "numbers" / "letters" / "common".
            "echo": Can be "all" / "common" / "none".
            "permit_pos": Can be True or False.
        """
        self.trigger_dict = None

        self.dmtex_suppress = (
            False  # an indicator that you should stop interfering with the terminal
        )
        self.buf = [0, ""]
        self.focus = 0
        self.spacerem = -1

    def check_activity(self) -> bool:
        self._active = hasattr(self.console, "connected")
        return self._active

    def write(self, strr=None, end="\n") -> None:
        if self.stdout_buf is None:
            self.stdout_buf = ""
        self.stdout_buf += (strr if strr is not None else "") + end
        del strr, end
        self._auto_flush()

    def nwrite(self, strr=None) -> None:
        if self.stdout_buf is None:
            self.stdout_buf = ""
        self.stdout_buf += strr if strr is not None else ""
        del strr
        self._auto_flush()

    def flush_writes(self, to_stdout=True) -> None:
        self._flush_to_bytes()
        if len(self.stdout_buf_b):
            data = None
            if to_stdout:
                self.console.write(self.stdout_buf_b)
            else:
                data = self.stdout_buf_b
                # Will fail if there is ansi in here
            self.stdout_buf_b = bytes()
            if to_stdout:
                del data
                return None
            else:
                return data
        else:
            return None

    def update_rem(self) -> None:
        if ("permit_pos" not in self.trigger_dict) or self.trigger_dict["permit_pos"]:
            self.spacerem = self.ctx_dict["line_len"] - self.detect_pos()[1]

    def clear_buffer(self) -> None:
        # Internal
        self.stdin_buf = None
        self.stdout_buf_b = bytes()

        # External
        if self.console.in_waiting:
            self.console.reset_input_buffer()
        if hasattr(self.console, "out_waiting") and self.console.out_waiting:
            self.console.reset_output_buffer()

    def backspace(self, n=1) -> None:
        """
        Arguably most used key
        """
        self._flush_to_bytes()
        for i in range(n):
            if len(self.buf[1]) - self.focus > 0:
                if not self.focus:
                    self.buf[1] = self.buf[1][:-1]
                    self.stdout_buf_b += b"\010 \010"
                    self.spacerem += 1
                else:
                    self.spacerem += 1
                    self.stdout_buf_b += b"\010"
                    insertion_pos = len(self.buf[1]) - self.focus - 1
                    self.buf[
                        1
                    ] = f"{self.buf[1][:insertion_pos]}{self.buf[1][insertion_pos + 1 :]}"  # backend
                    self.stdout_buf_b += bytes(
                        f"{self.buf[1][insertion_pos:]} {ESCK}{str(len(self.buf[1][insertion_pos:]) + 1)}D",
                        CONV,
                    )  # frontend
                    del insertion_pos
        self._auto_flush()

    def home(self) -> None:
        """
        Go to start of buf
        """
        self._flush_to_bytes()
        lb = len(self.buf[1])
        df = lb - self.focus
        if df > 0:
            self.focus = lb
        self.stdout_buf_b += b"\010" * df
        del lb, df
        self._auto_flush()

    def end(self) -> None:
        """
        Go to end of buf
        """
        self._flush_to_bytes()
        self.stdout_buf_b += bytes(f"{ESCK}1C" * self.focus, CONV)
        self.focus = 0
        self._auto_flush()

    def overflow_check(self) -> bool:
        if self.spacerem is -1:
            self.update_rem()
        return False if self.spacerem > 0 else True

    def delete(self, n=1) -> None:
        """
        Key delete. Like, yea, the del you have on your keyboard under insert
        """
        self._flush_to_bytes()
        for i in range(n):
            if len(self.buf[1]) > 0 and self.focus:
                if self.focus == len(self.buf[1]):
                    self.buf[1] = self.buf[1][1:]
                    self.stdout_buf_b += bytes(
                        f"{self.buf[1]} " + "\010" * self.focus, CONV
                    )
                    self.spacerem += 1
                    self.focus -= 1
                else:
                    insertion_pos = len(self.buf[1]) - self.focus
                    self.buf[
                        1
                    ] = f"{self.buf[1][:insertion_pos]}{self.buf[1][insertion_pos + 1 :]}"  # backend
                    self.stdout_buf_b += bytes(
                        f"{self.buf[1][insertion_pos:]} {ESCK}{str(len(self.buf[1][insertion_pos:]) + 1)}D",
                        CONV,
                    )  # frontend
                    self.spacerem += 1
                    self.focus -= 1
                    del insertion_pos
        self._auto_flush()

    def clear(self) -> None:
        """
        Clear the whole screen & goto top

        2J clears the current screen
        3J clears scrollback

        3J should have been enough, but some terminals do also need 2J,
        so doing both, just to be safe.
        """
        self._flush_to_bytes()
        self.stdout_buf_b += bytes(f"{ESCK}2J{ESCK}3J{ESCK}H", CONV)
        self._auto_flush()

    def clear_line(self, direct: bool = False) -> None:
        """
        Clear the current line.

        2K Clears the line and 0G sends us to it's start.
        """
        clstr = bytes(f"{ESCK}2K{ESCK}0G", CONV)
        if not direct:
            self._flush_to_bytes()
            self.stdout_buf_b += clstr
            self._auto_flush()
        else:
            self.console.write(clstr)

    def start(self) -> None:
        """
        Start the Jcurses system.
        """
        if self.enabled:
            self.stop()
        self.enabled = True
        self.dmtex_suppress = True

    def stop(self) -> None:
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

    def detect_size(self, timeout=0.3):
        """
        Detect terminal size. Returns [rows, collumns] on success.
        If the terminal is unavailable or unresponsive, return False.
        """
        if hasattr(self.console, "size"):
            return self.console.size
        res = False
        strr = ""
        cc = None
        resi = []
        prt = None
        try:
            # clearing stdin in case of fast pasting
            self.rem_gib()

            for i in range(3):
                self.get_hw(i)

            tm = monotonic()
            while (monotonic() - tm < timeout) and (len(resi) != 2):
                if self.console.in_waiting:
                    cc = str(self.console.read(1), CONV)
                    if cc == "\x1b":
                        cc = str(self.console.read(1), CONV)
                        if cc == "[":
                            prt = ""
                            while monotonic() - tm < timeout:
                                cc = str(self.console.read(1), CONV)
                                if cc.isdigit():
                                    prt += cc
                                elif cc == ";":
                                    resi.append(int(prt))
                                    break
                                else:
                                    tm += 2 * timeout
                            prt = ""
                            while monotonic() - tm < timeout:
                                cc = str(self.console.read(1), CONV)
                                if cc.isdigit():
                                    prt += cc
                                elif cc == "R":
                                    resi.append(int(prt))
                                    break
                                else:
                                    tm += 2 * timeout
            if len(resi) == 2:
                res = resi
                # Let's also update the move bookmarks.
                self.ctx_dict["bottom_left"] = [res[0], 1]
                self.ctx_dict["line_len"] = res[1]
                if ("permit_pos" not in self.trigger_dict) or self.trigger_dict[
                    "permit_pos"
                ]:
                    self.spacerem = res[1] - self.detect_pos()[1]
            else:
                self.console.reset_input_buffer()
        except KeyboardInterrupt:
            pass
        except:
            pass
        del strr, cc, resi, prt, timeout
        return res

    def detect_pos(self) -> list:
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

                self.get_hw(1)  # we need an empty stdin for this
                while not strr.endswith("R"):
                    strr += str(self.console.read(1), CONV)
                strr = strr[2:-1]  # this is critical as find will break with <esc>.
                res = [int(strr[: strr.find(";")]), int(strr[strr.find(";") + 1 :])]
                del strr
                d = False
            except ValueError:
                pass
        del d
        return res

    def rem_gib(self) -> None:
        """
        remove gibberrish from stdin when we need to read ansi escape codes
        """

        d = True  # done
        got = False  # we got at least a few

        while d:
            n = self.console.in_waiting
            if n:
                got = True
                if self.stdin_buf is None:
                    self.stdin_buf = self.console.read(n)
                else:
                    self.stdin_buf += self.console.read(n)
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
            self.console.write(bytes(f"{ESCK}s{ESCK}500B{ESCK}500C", CONV))
        elif act is 1:
            # ask position
            self.console.write(bytes(f"{ESCK}6n", CONV))
        elif act is 2:
            # go back to original position
            self.console.write(bytes(f"{ESCK}u", CONV))

    def training(self, opt=False) -> None:
        sleep(3)
        for i in range(0, 10):
            n = self.console.in_waiting
            if n:
                if not opt:
                    i = self.console.read(n)
                    for s in i:
                        print(str(s))
                else:
                    self.console.write(bytes(str(self.register_char()), CONV))
        self.console.write(b"\n\r")

    def register_char(self) -> list:
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
        n = self.console.in_waiting
        if n or self.stdin_buf is not None:
            i = None
            if self.stdin_buf is not None:
                i = self.stdin_buf
            else:
                self.stdin_buf = self.console.read(n)
                i = self.stdin_buf
                try:
                    for charr in i:
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
            self.stdin_buf = None
        return stack

    def is_interrupted(self) -> bool:
        res = False
        tempstack = self.register_char()
        if tempstack is not None:
            tempstack.reverse()
            if "ctrlC" in tempstack:
                res = True
                # We abandon this buffer
        del tempstack
        return res

    def input(self, prefix="") -> str:
        res = ""
        old_tr = self.trigger_dict.copy()
        self.trigger_dict.clear()
        self.trigger_dict.update(
            {
                "prefix": prefix,
                "enter": 0,
                "ctrlD": 0,
                "ctrlC": 1,
                "overflow": 1,
                "rest": "stack",
                "rest_a": "common",
                "echo": "common",
            }
        )
        res = ""
        while True:
            try:
                self.buf[1] = ""
                self.focus = 0
                self.program()
                if self.buf[0] is 0:
                    res = self.buf[1]
                    break
            except KeyboardInterrupt:
                pass
            except:
                pass
        self.trigger_dict = old_tr
        self.buf[1] = ""
        return res

    def program_non_blocking(self):
        """
        The main program, but doesnt block.
        None when no data.
        Depends on variables being already set.
        """
        if self.console.in_waiting:
            return self.program(nb=True)

    def program(self, nb=False) -> list:
        """
        The main program.
        Depends on variables being already set.
        """
        self.check_activity()
        if self._active and not self.console.connected:
            self.buf[0] = self.trigger_dict["idle"]
            self.softquit = True
            return self.buf
        self.softquit = False
        segmented = False
        self.buf[0] = 0
        self.termline()
        self.console.write(
            bytes(f"{ESCK}s{ESCK}1B{ESCK}1C{ESCK}u", CONV)
        )  # ESP32-Cx my beloved
        while (
            not self.softquit
        ):  # Dear lord, forgive me for the crime I am about to commit.
            try:
                while not self.softquit:
                    try:
                        while not self.softquit:
                            tempstack = self.register_char()
                            if tempstack:
                                tempstack.reverse()
                            elif self._active and not self.console.connected:
                                self.buf[0] = self.trigger_dict["idle"]
                                self.softquit = True
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
                                        self.console.write(b"\010")
                                        self.focus += 1
                                elif i == "right":
                                    if self.focus:
                                        self.console.write(bytes(f"{ESCK}1C", CONV))
                                        self.focus -= 1
                                elif self.trigger_dict["rest"] == "stack" and (
                                    self.trigger_dict["rest_a"] == "common"
                                    and not (
                                        i.startswith("ctrl") or i.startswith("alt")
                                    )
                                ):  # Arknights "PatriotExtra" theme starts playing
                                    if self.focus is 0:
                                        if self.trigger_dict["echo"] in {
                                            "common",
                                            "all",
                                        }:
                                            if not self.overflow_check():
                                                self.console.write(bytes(i, CONV))
                                                self.spacerem -= len(i)
                                                self.buf[1] += i
                                            else:
                                                if self.stdin_buf is None:
                                                    self.stdin_buf = i
                                                else:
                                                    self.stdin_buf += i
                                                while tempstack:
                                                    self.stdin_buf += tempstack.pop()
                                                self.softquit = True
                                                try:
                                                    self.buf[0] = self.trigger_dict[
                                                        "overflow"
                                                    ]
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
                                            self.console.write(bytes(d, CONV))

                                        steps_in = len(self.buf[1][insertion_pos:])

                                        for e in range(steps_in - 1):
                                            self.console.write(b"\010")

                                        del steps_in, insertion_pos
                                if nb and not tempstack:
                                    self.softquit = True
                    except KeyboardInterrupt:
                        self.buf[0] = self.trigger_dict["ctrlC"]
                        self.softquit = True
            except KeyboardInterrupt:
                self.buf[0] = self.trigger_dict["ctrlC"]
                self.softquit = True
            """
            The double try-except is needed because if the user holds down
            Ctrl + C on a native USB interface the code will still escape.
            """
            del tempstack
        del segmented, nb
        return self.buf

    def termline(self) -> None:
        self._flush_to_bytes()
        self.stdout_buf_b += bytes(
            self.trigger_dict["prefix"].replace("\n", "\n\r") + self.buf[1], CONV
        )
        if self.focus:
            self.stdout_buf_b += bytes(f"{ESCK}{self.focus}D", CONV)
        self.update_rem()
        self._auto_flush()

    def move(self, ctx=None, x=0, y=0) -> None:
        """
        Move to a specified coordinate or a bookmark.
        If you specified a bookmark, you can use x & y to add an offset.
        """
        self._flush_to_bytes()
        if ctx is None:
            x, y = max(1, x), max(1, y)
            self.stdout_buf_b += bytes(f"{ESCK}{y};{x}H", CONV)
        else:
            thectx = self.ctx_dict[ctx]
            self.stdout_buf_b += bytes(f"{ESCK}{thectx[1]};{thectx[0]}H", CONV)

            # out of bounds check for up and down
            if x + thectx[0] > 0:
                if thectx[0] > 0:
                    self.stdout_buf_b += bytes(f"{ESCK}{thectx[0]}B", CONV)
                else:
                    self.stdout_buf_b += bytes(f"{ESCK}{-thectx[0]}A", CONV)

            # out of bounds check for right and left
            if y + thectx[1] > 0:
                if thectx[1] > 0:
                    self.stdout_buf_b += bytes(f"{ESCK}{thectx[1]}C", CONV)
                else:  # left
                    self.stdout_buf_b += bytes(f"{ESCK}{-thectx[1]}D", CONV)

            del thectx
            self._auto_flush()

    def ctx_reg(self, namee) -> None:
        if ("permit_pos" not in self.trigger_dict) or self.trigger_dict["permit_pos"]:
            self.ctx_dict[namee] = self.detect_pos()

    def line(self, charr) -> None:
        # Will not work without a connected console.
        self.clear_line()
        tmpsz = self.detect_size()
        if tmpsz != False:
            self.stdout_buf_b += bytes(charr * tmpsz[1], CONV)
            self._auto_flush()
        del tmpsz

    def _flush_to_bytes(self) -> None:
        if self.stdout_buf is not None:
            self.stdout_buf_b += bytes(self.stdout_buf.replace("\n", "\n\r"), CONV)
            self.stdout_buf = None

    def _auto_flush(self) -> None:
        if not self.hold_stdout:
            self.flush_writes()
