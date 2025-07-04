class Remotes:
    class Protocol:
        def __init__(self, command, input_stream, output_stream, capabilities=[]):
            self.command = command
            self.input = input_stream
            self.output = output_stream

            self.input.flush()
            self.output.flush()

            self.caps_local = capabilities
            self.caps_remote = None
            self.caps_sent = False

        def capable(self, ability):
            return self.caps_remote is not None and ability in self.caps_remote

        def send_packet(self, line):
            if line is None:
                return self.output.write(b"0000")

            line = self.append_caps(line)

            size = len(line.encode("utf-8")) + 5
            header = f"{size:04x}"

            self.output.write(header.encode())
            self.output.write(line.encode())
            self.output.write(b"\n")
            self.output.flush()

        def recv_packet(self):
            import re

            head_bytes = self.input.read(4)

            try:
                head_str = head_bytes.decode("ascii")
            except UnicodeDecodeError:
                return None if not head_bytes else head_bytes

            if not re.match(r"^[0-9a-f]{4}$", head_str, re.IGNORECASE):
                return head_bytes

            size = int(head_str, 16)
            if size == 0:
                return None

            body = self.input.read(size - 4)
            if body.endswith(b"\n"):
                body = body[:-1]

            body_str = body.decode("utf-8", errors="replace")

            return self.detect_caps(body_str)

        def recv_until(self, terminator):
            """
            Generator yielding packets until the terminator is encountered.
            """
            while True:
                line = self.recv_packet()
                if line == terminator:
                    break
                yield line

        def append_caps(self, line):
            if self.caps_sent:
                return line

            self.caps_sent = True
            sep = " " if self.command == "fetch" else "\x00"

            caps = set(self.caps_local)
            if self.caps_remote:
                caps &= set(self.caps_remote)

            caps_str = " ".join(caps)
            return f"{line}{sep}{caps_str}" if caps_str else line

        def detect_caps(self, line):
            if self.caps_remote is not None:
                return line

            if self.command == "upload-pack":
                sep = " "
                parts_count = 3
            else:
                sep = "\x00"
                parts_count = 2

            parts = line.split(sep, parts_count)
            if len(parts) == parts_count:
                *main_parts, caps = parts
            else:
                main_parts = parts
                caps = ""

            self.caps_remote = caps.split() if caps else []
            return sep.join(main_parts)
