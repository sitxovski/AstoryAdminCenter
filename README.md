<div align="center">

**English** · [Русский](README.ru.md) · [العربية](README.ar.md)

### ❤️ Like the project? Support the hard work on [**Boosty**](https://boosty.to/sitxovski_yurii)

# Astory Admin Center

**A web panel to run the Astory game server — players, anti-cheat, events, releases and community in one place**

[Astory Client](https://github.com/sitxovski/AstoryClient) · [Astory Server](https://github.com/sitxovski/AstoryServer) · [Astory Admin Center](https://github.com/sitxovski/AstoryAdminCenter)

</div>

---

> ⚠️ **Disclaimer.** This package (Not whole project!) was built using **Claude Code** and may contain issues. Feel free to DM me on Discord (**@sitxovski**) to get support.

## What it can do

- 👤 **Players** — accounts, characters, inventories, item history, dupe search, who is online
- 🛡️ **Anti-cheat** — journal, daily report, auto-blocks, cases, chat log, name check
- 🎉 **Game** — exp / drop events, rankings, maintenance mode, shops and game data with rollback
- 🚀 **Releases** — release status, client crashes, release notes
- 💬 **Community** — Discord announcements and commands, player reports, Telegram alerts for the owner
- 📜 **Safety** — roles, two-factor login, an audit log of every action with undo

The panel runs on the game server (HTTPS) and is deployed from your PC over SSH. The look matches the game windows.

## Quick start

1. **Install** — run `Prerequisites\install_prerequisites.bat` on your PC and `... -Server` on the server ([details](Prerequisites/README.md)).
2. **Configure** — run `_setup\configure.bat` (server address, SSH key, Discord IDs — [where to get them](_setup/SETUP.md)).
   Run it in **all three** clones (AstoryClient, AstoryServer, AstoryAdminCenter): the panel and the bot use `AstoryClient\Tools\asda_paths.py`
   and `AstoryServer\Tools\Anticheat\db_connect.py`; the answers are reused, so the other clones ask only what is new.
3. **Deploy** — `python deploy\deploy_admin_center.py --skip-selftest`
   It copies the panel to the server and installs its SQL objects (`sql\*.sql`) by itself — you never run them by hand.
   (the deploy without `--skip-selftest` first runs the offline self-test, which needs SQL Server **LocalDB** on the PC and
   skips the checks that need files of the author's development environment — see [Prerequisites](Prerequisites/README.md#3-deploy--build)).
   After the first deploy run `AstoryServer\Prerequisites\setup_server.ps1 -SyncAdminBridge` on the server and restart the stack — it gives the game servers the bridge keys of the panel.
4. **Open** — `bat\AdminCenter.bat` → *tunnel*, then `https://localhost:17890/`

Full guide: [`GUIDE.md`](GUIDE.md) (in Russian).

Works together with [Astory Server](https://github.com/sitxovski/AstoryServer) (the game server it manages)
and [Astory Client](https://github.com/sitxovski/AstoryClient) (releases and crash reports).

## Credits

Made by **@sitxovski** (Discord).

Free to use for anything, no restrictions — [MIT License](LICENSE). **Just credit the original author — @sitxovski (Discord) —
and link to this repository when you copy, fork or reuse any part of it.**

---

<div align="center">

### ❤️ Support the hard work on [**Boosty**](https://boosty.to/sitxovski_yurii)

</div>
