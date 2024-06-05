from __future__ import annotations

import os
from asyncio import sleep
from dataclasses import dataclass
from datetime import datetime
from inspect import signature
from itertools import islice
from typing import Optional, List, Union, Callable, Any, Dict, Awaitable

from discord import Message, PartialEmoji, Emoji, ui, ButtonStyle, Interaction, AllowedMentions, Thread, Guild, \
    Reaction, Embed, Colour, TextChannel
from discord.abc import GuildChannel, Messageable
from discord.app_commands import describe
from discord.ext import tasks
from discord.ext.commands import Context, Greedy, hybrid_group, Cog
from discord.utils import get

from cache import DiscordTraverser, Cache, FunctionQueue, CacheEntry, MemoryCache
from converters import DatetimeConverter, discord_timestamp, lookup_emoji, TimestampStyle

# TODO; Python 3.12 (https://stackoverflow.com/questions/8991506/iterate-an-iterator-by-chunks-of-n-in-python)
def batched(iterable, n):
    "Batch data into tuples of length n. The last batch may be shorter."
    # batched('ABCDEFG', 3) --> ABC DEF G
    if n < 1:
        raise ValueError('n must be at least one')
    it = iter(iterable)
    while (batch := tuple(islice(it, n))):
        yield batch

class DynamicMessage: # TODO: Could make use of discord.DynamicItem
    message: Optional[Message] = None

    def __init__(self, queue: FunctionQueue, ctx: Context, on_send: Optional[Callable[[Context, Message], Awaitable[Any]]] = None, **kwargs: Callable[[], Any]):
        self.queue = queue
        self.ctx = ctx
        self.on_send = on_send
        self.kwargs = kwargs

    async def task(self):
        await sleep(0.5)
        await self.send()
    async def __aenter__(self) -> DynamicMessage:
        await self.send() # Send initial message
        self.queue.add_dynamic_worker(self.task)

        return self
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.send() # after done, send one more time

    # TODO; these should support async
    def params(self, func) -> Dict[str, Any]:
        func_params = filter(lambda param: param[0] in self.kwargs, signature(func).parameters.items())
        return dict(map(lambda param: (param[0], self.kwargs.get(param[0], None)()), func_params))

    async def send(self) -> Optional[Message]:
        async def _send() -> Optional[Message]:
            if self.message is None:
                self.message = await self.ctx.send(**self.params(self.ctx.send))
                return

            # if self.message.content == self.content(): return None

            await self.message.edit(**self.params(self.message.edit))

        await _send()
        self.message.guild = self.ctx.guild # Attach guild info (required for .create_thread)

        if not self.message: return None
        if self.on_send: await self.on_send(ctx=self.ctx, message=self.message)

        return self.message

class ReactionCounter(DiscordTraverser):

    @dataclass
    class Options:
        emojis: List[Union[PartialEmoji, Emoji, str]]
        guilds: Greedy[Guild] = None,
        channels: Greedy[Union[GuildChannel, Thread]] = None,
        before: Optional[datetime] = None,
        after: Optional[datetime] = None,
        skip_cache: Optional[bool] = False,

        def __str__(self):
            return (
                f'`after:` {discord_timestamp(self.after, default="None")}'
                f', `before:` {discord_timestamp(self.before, default="None")}'
                f', `channels:` {"None" if self.channels is None else ", ".join(map(lambda channel: channel.mention, self.channels))}'
                f', `skip_cache: {self.skip_cache}`'
                f''
            )

    message: Optional[Message] = None

    def __init__(self, ctx: Context, options: Options, cache: Cache):
        super().__init__(cache = MemoryCache() if options.skip_cache else cache)
        self.ctx = ctx
        self.options = options

    async def load_defaults(self) -> ReactionCounter:
        self.options.guilds = None  # TODO; Just ignore guild as an option for now
        if self.options.guilds is None and self.options.channels is None:
            if self.ctx.guild is not None:
                self.options.guilds = [self.ctx.guild]
            else:
                self.options.channels = [self.ctx.channel]

        # Lookup emojis
        self.options.emojis = [await lookup_emoji(ctx=self.ctx, emoji=emoji) for emoji in self.options.emojis]

        await self.push(self.options.guilds)
        await self.push(self.options.channels)
        
        return self

    async def count(self) -> None: await self.dump_exec()

    async def with_message(self, **kwargs):
        async with DynamicMessage(queue=self, ctx=self.ctx, **kwargs):
            await self.count()
    async def send(self, **kwargs) -> Optional[Message]:
        return await DynamicMessage(queue=self, ctx=self.ctx, **kwargs).send()

    def view(self) -> Optional[ui.View]:
        if self.done(): return None

        count = self
        class CountingView(ui.View):
            @ui.button(label='Cancel', style=ButtonStyle.red)
            async def cancel(self, interaction: Interaction, button: ui.Button):
                count.cancel()
                await interaction.response.send_message('Cancelled!', ephemeral=True)

        return CountingView()

    def header(self) -> str:
        return (
            f'**Counted {" ".join([f"`{self.cache.reactions.get_all(emoji=emoji).count():,}` {str(emoji)}" for emoji in self.options.emojis])} ...**'
            f'\n*so far in'
            f' {self.cache.reactions.count():,} reactions'
            f', {self.cache.messages.count():,} messages'
            f', {self.cache.categories.count():,} categories'
            f', {self.cache.forums.count():,} forums'
            f', {self.cache.messageables.count():,} messageables: ('
            f'{self.cache.text_channels.count():,} text channels'
            f', {self.cache.threads.count():,} threads'
            f', {self.cache.stages.count():,} stages'
            f', {self.cache.voice_channels.count():,} voice channels'
            f')'
            # f', {self.cache.users.count():,} users ({self.cache.users.filter(lambda user: user.bot).count():,} bots)'
            f'{f", {self.cache.guilds.count():,} guilds" if self.cache.guilds.count() > 1 else ""}'
            f'*'
            f'\n*with options:* {self.options}'
        )

    # def content_top(self) -> str:
    #     if not self.options.top or self.cache.users.empty(): return ""
    #
    #     users = self.cache.users.filter(lambda user: not user.bot)
    #
    #     return (
    #         f'{f"**Top**"}'
    #         f'\n1. {" ".join([f"`{users.reactions.get_all(emoji=emoji).count():,}` {str(emoji)}" for emoji in self.options.emojis])} @fadishawki (across `{users.messages.reactions.count():,} messages`)'
    #         f'\n*...30 more*'
    #     )


# TODO: Can python do this pretty without this copy-pasta? ; otherwise just use some dynamic classes
class Count(Cog):

    def __init__(self, client, cache: Cache):
        self.client = client
        self.global_cache = cache

    @hybrid_group()
    async def count(self, ctx: Context):
        raise NotImplementedError

    @count.command()
    @describe(channels="Channels", before="Count before date(time) ex: 2023-01-01", after="Count after date(time) ex: 2023-01-01", skip_cache="Whether to skip the cache and actively search through channels")
    async def reaction(
        self, ctx: Context,
        emojis: Greedy[Union[PartialEmoji, Emoji, str]],
        channels: Greedy[Union[GuildChannel, Thread]] = None, after: Optional[DatetimeConverter] = None, before: Optional[DatetimeConverter] = None, skip_cache: Optional[bool] = False,
    ):
        counter = await ReactionCounter(
            ctx=ctx, cache=self.global_cache,
            options=ReactionCounter.Options(emojis=emojis, channels=channels, skip_cache=skip_cache, after=after, before=before)
        ).load_defaults()

        # Some indication as to what is happening - not meant to be practical
        def content_checking_message() -> str:
            # TODO FILTER Message
            entry = counter.cache.messages.last()

            if counter.done(): return ""
            if entry is None: return ""

            message = entry.current
            return f'\n\n👀 {message.jump_url} - {discord_timestamp(message.created_at)}'

        await counter.with_message(
            content = lambda:
                f'{counter.header()}'
                f'{content_checking_message()}',
            view = counter.view,
            allowed_mentions = lambda: AllowedMentions(users=False, roles=False, everyone=False, replied_user=True),
            ephemeral=lambda: True
        )

    def reaction_command(self, name: str, emoji: Union[PartialEmoji, Emoji, str]) -> Cog:
        cmd = self

        class ReactionCommand(Cog):
            def __init__(self):
                # self.top_contributors.start()
                pass

            # @tasks.loop(hours=1)  # Lazily ensure update every hour, can update it from elsewhere
            # async def top_contributors(self):
            #

            @hybrid_group(name=name)
            @describe(before="ex: 2023-01-01", after="ex: 2023-01-01", skip_cache="Whether to skip the cache and actively search through channels")
            async def reaction_command_group(
                self, ctx: Context,
                channels: Greedy[Union[GuildChannel, Thread]] = None, after: Optional[DatetimeConverter] = None, before: Optional[DatetimeConverter] = None, skip_cache: Optional[bool] = False,
            ):
                return await cmd.reaction(
                    ctx=ctx, emojis=[emoji],
                    channels=channels,after=after,before=before,skip_cache=skip_cache
                )

            # @reaction_command_group.command()
            # async def top(
            #     self, ctx: Context,
            #     channels: Greedy[Union[GuildChannel, Thread]] = None, after: Optional[DatetimeConverter] = None,
            #     before: Optional[DatetimeConverter] = None, skip_cache: Optional[bool] = False,
            # ):
            #     if not cmd.client.is_ready(): return
            #
            #     channel = await cmd.client.fetch_channel(os.environ.get("SEMF_TOP_CONTRIBUTIONS_CHANNEL", 1207430024660262932))
            #     if not isinstance(channel, TextChannel): return
            #
            #     message = None
            #     last_message = True
            #     async for m in channel.history(limit=100):
            #         if message is not None: last_message = False
            #
            #         if m.author == cmd.client.user and ('Top Contributors' in m.content):
            #             last_message = message
            #
            #     # TODO: Move this top thing elsewhere
            #     counter = await ReactionCounter(
            #         ctx=ctx, cache=cmd.global_cache,
            #         options=ReactionCounter.Options(emojis=[emoji], channels=channels, skip_cache=skip_cache, after=after, before=before)
            #     ).load_defaults()
            #
            #     top = (
            #         counter.cache.reactions
            #         .get_all(emoji=counter.options.emojis[0])  # TODO Multi-emoji for general cmds
            #         .group_by(lambda reaction_entry: int(reaction_entry.current.message.author.id))
            #         .filter(lambda grouped_entry: (
            #               # Number of reactions
            #               grouped_entry.current[1].count()
            #               # - number of reactions by one-self TODO: could make optional
            #               - grouped_entry.current[1].filter(
            #               lambda reaction_entry: reaction_entry.current.me).count()
            #           ) > 0)
            #         .sort(lambda grouped_entry: -grouped_entry.current[1].count())
            #     )
            #
            #     await counter.count()
            #
            #     if message is None or not last_message:  # TODO; Could be better check perhaps dynamicitem?
            #         print('create it')
            #         # await channel.send('test')
            #         m = "\n".join([
            #             f'**#{index + 1}: <@{author_entry.current}>: **'
            #             f'{" ".join([f"`{reaction.count - reactions_cache.filter(lambda reaction_entry: reaction_entry.current.me).count():,}` {str(reaction.emoji)}" for reaction in reactions_cache.current()])}'
            #
            #             for index, (author_entry, reactions_cache) in enumerate(list(top.current())[:10])
            #         ])
            #         await channel.send(
            #          allowed_mentions=lambda: AllowedMentions(users=False, roles=False, everyone=True,replied_user=True),
            #             content=f'## **Top {counter.options.emojis[0]} Contributors**'
            #                     f'\n{m}',
            #         )
            #         return
            #
            #     print('edit it')

            @reaction_command_group.command()
            @describe(before="ex: 2023-01-01", after="ex: 2023-01-01", skip_cache="Whether to skip the cache and actively search through channels")
            async def list(
                self, ctx: Context,
                channels: Greedy[Union[GuildChannel, Thread]] = None, after: Optional[DatetimeConverter] = None, before: Optional[DatetimeConverter] = None, skip_cache: Optional[bool] = False,
            ):
                counter = await ReactionCounter(
                    ctx=ctx, cache=cmd.global_cache,
                    options=ReactionCounter.Options(emojis=[emoji], channels=channels, skip_cache=skip_cache,after=after, before=before)
                ).load_defaults()

                # TODO DOUBLE CHECK SELFCOUNT
                # TODO EXCLUDE PRIVATE

                number_of_entries: int = 3
                content_length = 300
                # max embed size is currently 6000
                # max embed field value length is 1024 (currently)

                top = (
                    counter.cache.reactions
                    .get_all(emoji=counter.options.emojis[0]) # TODO Multi-emoji for general cmds
                    .group_by(lambda reaction_entry: reaction_entry.current.message)
                    .filter(lambda grouped_entry: (
                        # Number of reactions
                        grouped_entry.current[1].count()
                        # - number of reactions by one-self TODO: could make optional
                        - grouped_entry.current[1].filter(
                        lambda reaction_entry: reaction_entry.current.me).count()
                    ) > 0)
                    .sort(lambda grouped_entry: -grouped_entry.current[1].count())
                )

                def embed(index: int, message_entry: CacheEntry[Message], reactions_cache: Cache[Reaction]) -> Embed:
                    message = message_entry.current

                    def content() -> str:
                        if message.content.strip(): return f'{message.content[:content_length]}{"..." if len(message.content) > content_length else ""}'
                        if message.attachments: return str(message.attachments[0])
                        return ""

                    embed = Embed(
                        timestamp=None,
                        url=None,
                        type='rich',
                        color=Colour.orange(),
                        description=f'**'
                                    f'#{index + 1}: {" ".join([f"`+ {reaction.count - reactions_cache.filter(lambda reaction_entry: reaction_entry.current.me).count():,}` {str(reaction.emoji)}" for reaction in reactions_cache.current()])}'
                                    f' - {message.author.mention} in {message.jump_url}'
                                    f'**',
                    )
                    embed.add_field(
                        name=f'{discord_timestamp(message.created_at)}',
                        value=f'{content()}'
                              f'\n\n{" ".join([f"`{reaction.count:,}` {str(reaction.emoji)}" for reaction in message.reactions])}',
                        inline=False
                    )

                    return embed

                # Dynamic counter for the sender
                await counter.with_message(
                    content=lambda:
                        f'{counter.header()}'
                        f'\n'
                        f'## **'
                        f'A total of {" ".join([f"`{counter.cache.reactions.get_all(emoji=emoji).count():,}` {str(emoji)}" for emoji in counter.options.emojis])}'
                        f' awarded across {top.count():,} messages from'
                        f' {discord_timestamp(counter.options.after, style=TimestampStyle.D, default="Infinity")}'
                        f' to {discord_timestamp(counter.options.before, style=TimestampStyle.D, default="Beyond")}'
                        f'**',
                    view=counter.view,
                    embeds=lambda: [embed(index, message_entry, reactions_cache) for index, (message_entry, reactions_cache) in enumerate(list(top.current())[:number_of_entries])],
                    allowed_mentions=lambda: AllowedMentions(users=False, roles=False, everyone=False,replied_user=True),
                    ephemeral=lambda: True
                )

                # To a message & thread
                async def on_send(ctx: Context, message: Message):
                    entries_to_thread = list(top.current())[number_of_entries:]
                    if not entries_to_thread: return

                    max_embeds = 10 # max set by discord

                    thread = await message.create_thread(
                        name=f'A total of {" ".join([f"{counter.cache.reactions.get_all(emoji=emoji).count():,} {emoji.name}" for emoji in counter.options.emojis])}'
                             f' awarded across {top.count():,} messages'
                    )

                    last_message: Optional[Message] = None
                    index = number_of_entries
                    for batch in batched(entries_to_thread, max_embeds):
                        start_index = index
                        index += len(batch)

                        last_message = await thread.send(
                            reference=last_message, # Does the reply
                            content=f'**#{start_index + 1} - #{index}**',
                            embeds=[embed(start_index + batch_index, message_entry, reactions_cache) for
                                    batch_index, (message_entry, reactions_cache) in
                                    enumerate(batch)],
                            allowed_mentions=AllowedMentions(users=False, roles=False, everyone=False, replied_user=True),
                        )

                await counter.send(
                    content=lambda:
                        f'## **'
                        f'@everyone A total of {" ".join([f"`{counter.cache.reactions.get_all(emoji=emoji).count():,}` {str(emoji)}" for emoji in counter.options.emojis])}'
                        f' awarded across {top.count():,} messages from'
                        f' {discord_timestamp(counter.options.after, style=TimestampStyle.D, default="Infinity")}'
                        f' to {discord_timestamp(counter.options.before, style=TimestampStyle.D, default="Beyond")}'
                        f'**',
                    view=counter.view,
                    embeds=lambda: [embed(index, message_entry, reactions_cache) for
                                    index, (message_entry, reactions_cache) in
                                    enumerate(list(top.current())[:number_of_entries])],
                    allowed_mentions=lambda: AllowedMentions(users=False, roles=False, everyone=True,replied_user=True),
                    on_send=on_send
                )



            # @reaction_command_group.command()
            # @describe(before="ex: 2023-01-01", after="ex: 2023-01-01", skip_cache="Whether to skip the cache and actively search through channels")
            # async def list(
            #     self, ctx: Context,
            #     channels: Greedy[Union[GuildChannel, Thread]] = None, after: Optional[DatetimeConverter] = None, before: Optional[DatetimeConverter] = None, skip_cache: Optional[bool] = False,
            # ):
            #     counter = await ReactionCounter(
            #         ctx=ctx, cache=cmd.global_cache,
            #         options=ReactionCounter.Options(emojis=[emoji], channels=channels, skip_cache=skip_cache,after=after, before=before)
            #     ).load_defaults()
            #
            #     number_of_entries = 5
            #     content_length = 300
            #     # max embed size is currently 6000
            #     # max embed field value length is 1024 (currently)
            #
            #     def embed() -> Embed:
            #         emoji = counter.options.emojis[0] # TODO Multi-emoji for general cmds
            #
            #         # TODO: THIS NEEDS TO GO - through .filter in cache, needs group as well
            #         top = (
            #             counter.cache.reactions
            #                .get_all(emoji=emoji)
            #                .group_by(lambda reaction_entry: reaction_entry.current.message)
            #                .filter(lambda grouped_entry: (
            #                    # Number of reactions
            #                    grouped_entry.current[1].count()
            #                    # - number of reactions by one-self TODO: could make optional
            #                    - grouped_entry.current[1].filter(lambda reaction_entry: reaction_entry.current.me).count()
            #                ) > 0)
            #                .sort(lambda grouped_entry: -grouped_entry.current[1].count())
            #         )
            #
            #         embed = Embed(
            #             timestamp=None,
            #             url=None,
            #             type='rich',
            #             title=None,
            #             color=Colour.orange(),
            #             description=f'## **'
            #                         f'A total of {" ".join([f"`{counter.cache.reactions.get_all(emoji=emoji).count():,}` {str(emoji)}" for emoji in counter.options.emojis])}'
            #                         f' awarded across {top.count():,} messages from'
            #                         f' {discord_timestamp(counter.options.after, style=TimestampStyle.D, default="Infinity")}'
            #                         f' to {discord_timestamp(counter.options.before, style=TimestampStyle.D, default="Beyond")}'
            #                         f'**',
            #         )
            #
            #         i = 0
            #         for message_entry, reactions_cache in list(top.current())[:number_of_entries]:
            #             i += 1
            #
            #             message = message_entry.current
            #             def content() -> str:
            #                 if message.content.strip(): return f'{message.content[:content_length]}{"..." if len(message.content) > content_length else ""}'
            #                 if message.attachments: return str(message.attachments[0])
            #                 return ""
            #
            #             embed.add_field(
            #                 name=f'#{i}: {" ".join([f"`{reaction.count - reactions_cache.filter(lambda reaction_entry: reaction_entry.current.me).count():,}x` {str(reaction.emoji)}" for reaction in reactions_cache.current()])}',
            #
            #                 value=f'*{message.author.mention} in {message.jump_url} ({discord_timestamp(message.created_at)})*'
            #                       f'\n\n{content()}'
            #                       f'\n{" ".join([f"`{reaction.count:,}` {str(reaction.emoji)}" for reaction in message.reactions])}',
            #                 inline=False
            #             )
            #
            #         return embed
            #
            #     # def embed(message) -> Embed:
            #     #     return "\n".join([f'- {message.jump_url} - {discord_timestamp(message.created_at)}' for message, reactions in counter.messages(emoji=counter.options.emojis[0])])
            #
            #     await counter.with_message(
            #         content=lambda:
            #             f'{counter.header()}',
            #         view=counter.view,
            #         embeds=lambda: [embed()],
            #         allowed_mentions=lambda: AllowedMentions(users=False, roles=False, everyone=False,replied_user=True),
            #         ephemeral=lambda: True
            #     )

        return ReactionCommand()