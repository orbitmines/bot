<div align="center">  

# OrbitMines Bot
*Automated logistics: Platform interoperability.*

</div>

---

- [x] Initial setup by hand
- [ ] Incorporate in the Library later

## What platforms are supported?
[Discord](https://discord.com/developers/docs/) ([discord.py](https://github.com/Rapptz/discord.py), [rate limits](https://discord.com/developers/docs/topics/rate-limits#:~:text=global%22%3A%20true%20%7D-,Global%20Rate%20Limit,rate%20limit%20on%20a%20route.)), [Twitch](), [X (Twitter)](), [YouTube](), [Cloudflare](), [GitHub](https://github.com/apps/orbitmines), [GitLab](https://gitlab.com/groups/orbitmines/-/settings/applications), [LinkedIn](https://www.linkedin.com/developers/apps), [Meta: Instagram/Facebook](https://developers.facebook.com/apps/), [Substack](https://orbitmines.substack.com/), [NPM](https://www.npmjs.com/org/orbitmines)

*For more information on this (and other) interoperability, see [OrbitMines' Library](https://github.com/orbitmines/library)*.

---

## Local setup

```shell
git clone git@github.com:orbitmines/bot.git \
&& cd ./bot
```

*Install dependencies*
```shell
python3 -m pip install -U discord.py
```

*(first setup) Generating an oauth url to add the bot to a server*
```shell
DISCORD_CLIENT_ID="..." \
DISCORD_TOKEN="..." \
python3 ./bot/oauth2_url.py
```

*Run bot:*
```shell
# DISCORD_SKIP_HOOK=1 Skips manually syncing the Discord Interaction (i.e. AppCommands)`
DISCORD_SKIP_HOOK=0 \
DISCORD_GUILD_ID=1055502602365845534 \
BOT_CACHE_GIT_REPOSITORY="git@github.com:orbitmines/discord-mirror.git" \
BOT_CACHE_GIT_DIRECTORY="./.orbitmines/cache/git" \
BOT_CACHE_GIT_BRANCH="main" \
DISCORD_CLIENT_ID="..." \
DISCORD_TOKEN="..." \
python3 ./bot/run.py
```

---

## License Magic

I'm not convinced putting licenses on the repo's in the usual case is anything other than *Minecraft servers putting "Not affiliated with Mojang" in their stores* just because everyone else does it. But here: after doing absolutely no research into the international ramifications: [LICENSE](./LICENSE) a license for those who like to look at them. Try to reason to what that applies in this repository, obviously that doesn't cover everything not made by me or other contributions to OrbitMines or something. Just put a reference to me or this project somewhere if it's remotely interesting to you.