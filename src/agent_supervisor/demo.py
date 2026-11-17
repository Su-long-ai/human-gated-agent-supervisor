from pathlib import Path
import shutil

from .supervisor import Supervisor


def main() -> None:
    root = Path("demo_state")
    if root.exists():
        shutil.rmtree(root)

    sup = Supervisor(root)
    sup.bootstrap_main()
    sup.create_round("MAIN_AGENT", "Audit a small project and report findings")
    sup.confirm_project("MAIN_AGENT")
    sup.confirm_model("MAIN_AGENT")
    sup.mark_sent("MAIN_AGENT")

    current = sup.current_round("MAIN_AGENT")
    sup.write_heartbeat(
        "MAIN_AGENT",
        current.lease_id,
        "RUNNING",
        progress="reading project files",
    )
    final = sup.commit_round(
        "MAIN_AGENT",
        current.lease_id,
        result="audit complete",
        checkpoint="all findings persisted",
    )
    print(final.state.value)
    print(root.resolve())


if __name__ == "__main__":
    main()
