import tkinter as tk
import traceback
from tkinter import messagebox

from styles.theme import apply_theme
from statforge_tk.db import Database
from statforge_tk.ui import StatForgeApp


def main() -> None:
    db = Database()
    root = tk.Tk()
    apply_theme(root)

    def handle_tk_exception(exc: type[BaseException], val: BaseException, tb: object) -> None:
        traceback_text = "".join(traceback.format_exception(exc, val, tb))
        print("[StatForge] Unhandled Tk callback exception:")
        print(traceback_text)
        try:
            messagebox.showerror("StatForge Error", f"{val}\n\nSee terminal output for details.")
        except Exception:
            pass

    root.report_callback_exception = handle_tk_exception  # type: ignore[assignment]

    app = StatForgeApp(root, db)

    def on_close() -> None:
        app._video_release_capture()
        db.close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
