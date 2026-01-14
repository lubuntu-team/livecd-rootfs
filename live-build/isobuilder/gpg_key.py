import pathlib
import subprocess

key_conf = """\
%no-protection
Key-Type: eddsa
Key-Curve: Ed25519
Key-Usage: sign
Name-Real: Ubuntu ISO One-Time Signing Key
Name-Email: noone@nowhere.invalid
Expire-Date: 0
"""


class EphemeralGPGKey:

    def __init__(self, logger, gpghome):
        self.logger = logger
        self.gpghome = gpghome

    def _run_gpg(self, cmd, **kwargs):
        return self.logger.run(
            ["gpg", "--homedir", self.gpghome] + cmd, check=True, **kwargs
        )

    def create(self):
        with self.logger.logged("creating gpg key ...", done_msg="... done"):
            self.gpghome.mkdir(mode=0o700)
            self._run_gpg(
                ["--gen-key", "--batch"],
                input=key_conf,
                text=True,
            )

    def sign(self, path: pathlib.Path):
        with self.logger.logged(f"signing {path}"):
            with path.open("rb") as inp:
                with pathlib.Path(str(path) + ".gpg").open("wb") as outp:
                    self._run_gpg(
                        [
                            "--no-options",
                            "--batch",
                            "--no-tty",
                            "--armour",
                            "--digest-algo",
                            "SHA512",
                            "--detach-sign",
                        ],
                        stdin=inp,
                        stdout=outp,
                    )

    def export_public(self) -> str:
        return self._run_gpg(
            ["--export", "--armor"],
            stdout=subprocess.PIPE,
            text=True,
        ).stdout
