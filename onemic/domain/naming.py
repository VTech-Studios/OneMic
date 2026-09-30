from __future__ import annotations

from dataclasses import dataclass

PREFIX = "onemic"
MIX_TAP = "mix"


def is_onemic_node(name: str) -> bool:
    """Recognise nodes this application created, whichever mic they belong to.

    @param name: a node.name property.
    @return: True for any node under the OneMic prefix.
    """
    return name.startswith(f"{PREFIX}.")


def is_tap(name: str) -> bool:
    """Recognise metering taps, which belong to a running window rather than to a mic.

    @param name: a node.name property.
    @return: True for any OneMic tap node.
    """
    return is_onemic_node(name) and ".tap." in name


def mic_slug(name: str) -> str | None:
    """Recognise a virtual mic node, whichever mic it is.

    Mic nodes are the only OneMic nodes with nothing after the slug, which
    lets a mic left live by an earlier run be found and removed.

    @param name: a node.name property.
    @return: the mic's slug, or None if the node is not a OneMic mic.
    """
    if not is_onemic_node(name):
        return None
    rest = name.removeprefix(f"{PREFIX}.")
    return None if "." in rest else rest


@dataclass(frozen=True)
class NodeNames:
    """Every PipeWire node name used by one mic, derived from its slug.

    The graph itself is the record of what is running. Deriving every name
    from the slug means a restarted application can find a mic it left live
    without any state file. Slugs never contain dots, so the dot separators
    keep one mic's names from ever matching another's.
    """

    slug: str

    @property
    def mic(self) -> str:
        return f"{PREFIX}.{self.slug}"

    @property
    def mix_tap(self) -> str:
        return self.tap(MIX_TAP)

    def stage_input(self, input_id: str) -> str:
        return f"{self.mic}.in.{input_id}"

    def stage_output(self, input_id: str) -> str:
        return f"{self.stage_input(input_id)}.out"

    def tap(self, key: str) -> str:
        return f"{self.mic}.tap.{key}"

    def owns(self, name: str) -> bool:
        """Tell whether a node belongs to this mic.

        @param name: a node.name property.
        @return: True for the mic itself and every node named under it.
        """
        return name == self.mic or name.startswith(f"{self.mic}.")

    def stage_id(self, name: str) -> str | None:
        """Recover the input id from a gain stage's node name.

        Lets stale stages be found and stopped after their input was removed.

        @param name: a node.name property.
        @return: the input id, or None if the node is not one of this mic's stages.
        """
        marker = f"{self.mic}.in."
        if not name.startswith(marker):
            return None
        return name.removeprefix(marker).removesuffix(".out")
