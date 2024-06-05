import datetime
import datetime
import logging.handlers
import os
from typing import Union, Optional, Sequence

import discord
from discord import Permissions, Activity, Status, ActivityType, TextChannel, NotFound
from discord.abc import Messageable
from discord.ext import commands, tasks
from discord.utils import oauth_url, get

from Count import Count
from cache import Cache, cached_event, MemoryCache, GitCache

# TODO; All the environment variable gets are not secured/typed checked unless python provides it, just dumb string copying

SEMFCOIN_EMOJI = discord.PartialEmoji(name=os.environ.get("SEMF_SEMFCOIN_EMOJI", 'semfcoin'))
PRIMARY_GUILD = discord.Object(id=os.environ.get("DISCORD_GUILD_ID", 844566471501414463))

# https://discordpy.readthedocs.io/en/latest/logging.html
discord.utils.setup_logging(level=logging.INFO)

# https://discordpy.readthedocs.io/en/latest/intents.html
# intents = bot.Intents.default()
intents = discord.Intents.all()
# intents.message_content = True
# intents.members = True
# intents.reactions = True
# intents.guilds = True
# intents.messages = True
# intents.emojis = True
# intents.emojis_and_stickers = True
# intents.moderation = True
# intents.invites = True
# intents.integrations = True
# intents.webhooks = True
# intents.guild_scheduled_events = True

# https://discordpy.readthedocs.io/en/latest/api.html#permissions
default_permissions = discord.Permissions.all()

class Client(commands.Bot):

    def __init__(self, cache: Cache, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache = cache
    async def setup_hook(self) -> None:
        if os.environ.get("DISCORD_SKIP_HOOK", "0") == "1": return

        print(f'Setting up hook (Might take a bit)')

        # for extension in self.initial_extensions:
        #     await self.load_extension(extension)

        if PRIMARY_GUILD.id:
            self.tree.copy_global_to(guild=PRIMARY_GUILD)
            await self.tree.sync(guild=PRIMARY_GUILD)

    # Client
    async def start(self, *args) -> None:
        print(f'Initializing caches before starting Discord client')
        await self.cache.initialize()
        print(f'Starting Discord client')
        await super().start(*args)

    async def on_ready(self):
        print(f'We have logged in as {self.user}')

        await self.change_presence(activity = Activity(
            type = ActivityType.custom,
            name = "SEMF",
            state = "👀",
        ), status = Status.online)

    # Messages
    @cached_event
    async def on_message(self, message: discord.Message):
        # if message.author == self.user:
        #     return
        #
        # if message.content.startswith('$hello'):
        #     await message.channel.send('Hello!')
        pass
    @cached_event
    async def on_raw_message_edit(self, message: discord.RawMessageUpdateEvent):
        pass
    @cached_event
    async def on_raw_message_delete(self, message: discord.RawMessageDeleteEvent):
        pass
    @cached_event
    async def on_raw_bulk_message_delete(self, message: discord.RawBulkMessageDeleteEvent):
        pass

    # Reactions
    @cached_event
    async def on_raw_reaction_add(self, reaction: discord.RawReactionActionEvent):
        pass
    @cached_event
    async def on_raw_reaction_remove(self, reaction: discord.RawReactionActionEvent):
        pass
    @cached_event
    async def on_raw_reaction_clear(self, reaction: discord.RawReactionClearEvent):
        pass
    @cached_event
    async def on_raw_reaction_clear_emoji(self, reaction: discord.RawReactionClearEmojiEvent):
        pass

    # Members
    @cached_event
    async def on_member_join(self, member: discord.Member):
        pass
    @cached_event
    async def on_raw_member_remove(self, member: discord.RawMemberRemoveEvent):
        pass
    @cached_event
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        pass
    @cached_event
    async def on_user_update(self, before: discord.User, after: discord.User):
        pass
    @cached_event
    async def on_member_ban(self, guild: discord.Guild, user: Union[discord.User, discord.Member]):
        pass
    @cached_event
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        pass
    # async def on_presence_update(self, before: bot.Member, after: bot.Member):
    #     pass

    # Channels
    @cached_event
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        pass
    @cached_event
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        pass
    @cached_event
    async def on_guild_channel_pins_update(self, channel: Union[discord.abc.GuildChannel, discord.Thread], last_pin: Optional[datetime.datetime]):
        pass

    # Threads
    @cached_event
    async def on_thread_create(self, thread: discord.Thread):
        pass
    @cached_event
    async def on_thread_join(self, thread: discord.Thread):
        pass
    @cached_event
    async def on_raw_thread_update(self, payload: discord.RawThreadUpdateEvent):
        pass
    @cached_event
    async def on_raw_thread_delete(self, payload: discord.RawThreadDeleteEvent):
        pass
    @cached_event
    async def on_thread_member_join(self, member: discord.ThreadMember):
        pass
    @cached_event
    async def on_thread_member_remove(self, member: discord.ThreadMember):
        pass
    @cached_event
    async def on_raw_thread_member_remove(self, payload: discord.RawThreadMembersUpdate):
        pass

    # Integrations (https://support.discord.com/hc/en-us/articles/360045093012-Server-Integrations-Page)
    async def on_integration_create(self, integration: discord.Integration):
        pass
    async def on_integration_update(self, integration: discord.Integration):
        pass
    async def on_guild_integration_update(self, integration: discord.Integration):
        pass
    async def on_guild_integrations_update(self, guild: discord.Guild):
        pass
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        pass
    async def on_raw_integration_delete(self, payload: discord.RawIntegrationDeleteEvent):
        pass

    # Scheduled Events
    @cached_event
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent):
        pass
    @cached_event
    async def on_scheduled_event_delete(self, event: discord.ScheduledEvent):
        pass
    @cached_event
    async def on_scheduled_event_update(self, before: discord.ScheduledEvent, after: discord.ScheduledEvent):
        pass
    @cached_event
    async def on_scheduled_event_user_add(self, event: discord.ScheduledEvent, user: discord.User):
        pass
    @cached_event
    async def on_scheduled_event_user_remove(self, event: discord.ScheduledEvent, user: discord.User):
        pass

    # Stages
    @cached_event
    async def on_stage_instance_create(self, stage_instance: discord.StageInstance):
        pass
    @cached_event
    async def on_stage_instance_delete(self, stage_instance: discord.StageInstance):
        pass
    @cached_event
    async def on_stage_instance_update(self, stage_instance: discord.StageInstance):
        pass

    # Roles
    @cached_event
    async def on_guild_role_create(self, role: discord.Role):
        pass
    @cached_event
    async def on_guild_role_delete(self, role: discord.Role):
        pass
    @cached_event
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        pass

    # Guilds
    async def on_guild_available(self, guild: discord.Guild):
        pass
    async def on_guild_unavailable(self, guild: discord.Guild):
        pass
    @cached_event
    async def on_guild_join(self, guild: discord.Guild):
        pass
    @cached_event
    async def on_guild_remove(self, guild: discord.Guild):
        pass
    @cached_event
    async def on_guild_update(self, guild: discord.Guild):
        pass
    @cached_event
    async def on_guild_emojis_update(self, guild: discord.Guild, before: Sequence[discord.Emoji], after: Sequence[discord.Emoji]):
        pass
    @cached_event
    async def on_guild_stickers_update(self, guild: discord.Guild, before: Sequence[discord.GuildSticker], after: Sequence[discord.GuildSticker]):
        pass
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        pass
    @cached_event
    async def on_invite_create(self, invite: discord.Invite):
        pass
    @cached_event
    async def on_invite_delete(self, invite: discord.Invite):
        pass

async def oauth2_url(client: Client = Client(intents=intents, command_prefix='$', cache = MemoryCache()), permissions: Permissions = default_permissions) -> str:
    # await client.login(os.environ["DISCORD_TOKEN"])

    return oauth_url(os.environ["DISCORD_CLIENT_ID"], permissions = permissions, scopes = ['bot'])


async def run(client: Client = Client(
    intents=intents,
    command_prefix='$',
    cache = MemoryCache(mirrors=[
        GitCache(
            repository=os.environ["BOT_CACHE_GIT_REPOSITORY"], # Don't put a default here for safety
            directory=os.environ.get("BOT_CACHE_GIT_DIRECTORY", './.bot/cache/git'),
            branch=os.environ.get("BOT_CACHE_GIT_BRANCH", 'main')
        )
    ])
)):
    async with client:
        # Commands (https://discordpy.readthedocs.io/en/stable/ext/commands/cogs.html)
        count = Count(client=client, cache=client.cache)
        await client.add_cog(count)
        await client.add_cog(count.reaction_command(SEMFCOIN_EMOJI.name, SEMFCOIN_EMOJI))

        await client.start(os.environ["DISCORD_TOKEN"])