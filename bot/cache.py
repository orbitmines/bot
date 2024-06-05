from __future__ import annotations

import base64
import functools
import json
import os
import subprocess
import traceback
from asyncio import Queue, create_task
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from inspect import isclass
from itertools import groupby, chain
from pathlib import Path
from textwrap import wrap
from typing import Optional, AsyncIterator, Iterable, Generic, TypeVar, Callable, Any, Deque, List, Awaitable, Dict, \
    Tuple

from discord import Message, Guild, Thread, User, Reaction, CategoryChannel, StageChannel, ForumChannel, VoiceChannel, \
    TextChannel, Member
from discord.abc import Messageable, GuildChannel
from discord.mixins import Hashable
from discord.utils import get, find


def queue(method):
    async def _queue(self, *args, **kwargs) -> None:
        self.put_nowait(lambda: method(self, *args, **kwargs))

    return _queue

# TODO Python must have better ways of doing this
class FunctionQueue(Queue):

    def add_dynamic_worker(self, func: Callable[[], Awaitable[Any]]):
        async def task():
            try:
                while True:
                    await func()
            except Exception as e:
                print(f"Task failed with error: {e}")
                print(traceback.format_exc())
                raise

        self.workers.append(create_task(task()))
    def add_worker(self):
        async def do_task():
            try:
                func = await self.get()
                await func()

                self.task_done()
            except Exception as e:
                print(f"Task failed with error: {e}")
                print(traceback.format_exc())

        self.add_dynamic_worker(do_task)

    def __init__(self):
        super().__init__()
        self.workers = deque()
        self.exec = None

    async def dump_exec(self):
        for i in range(3):
            self.add_worker()

        self.exec = create_task(self.join())
        await self.exec

        self.cancel()

    def done(self) -> bool:
        return len(self.workers) == 0 and self.empty()
    def cancel(self) -> None:
        for worker in self.workers:
            worker.cancel()

        if self.exec is not None: self.exec.cancel()

        self.exec = None
        self.workers.clear()
        self._init(0) # clears the queue


TObject = TypeVar('TObject')
TTarget = TypeVar('TTarget')


# TODO; No tuple unpacking (lambda (message, reactions):
class CacheEntry(Generic[TObject]):

    def __init__(self, current: TObject):
        self.current = current
        # if isinstance(current, Reaction):
        #     self.current = CachedReaction(reaction=current) # Proxied reaction for additional functionality
        # else:

    async def live(self) -> TObject:
        raise NotImplementedError

    # TODO: Just this for now until we have a better idea of what to do with an offline mirror\
    @property
    def id(self) -> int | str:
        if not hasattr(self.current, 'id'): raise NotImplementedError(f'No "id" property is defined on {type(self.current)}')
        return self.current.id

    def __eq__(self, other: object) -> bool:
        if isinstance(other, CacheEntry): return self.id == other.id
        return self.id == CacheEntry(current=other).id  # TODO Might need to check object type here, but probably not
    
    # TODO: Just isolate to this until we know what to do
    def is_event(self) -> bool: return isinstance(self.current, Event)
    def is_user(self) -> bool: return isinstance(self.current, User)
    def is_member(self) -> bool: return isinstance(self.current, Member)
    def is_reaction(self) -> bool: return isinstance(self.current, Reaction)
    def is_message(self) -> bool: return isinstance(self.current, Message)
    def is_guild(self) -> bool: return isinstance(self.current, Guild)
    def is_channel(self) -> bool: return isinstance(self.current, GuildChannel)
    def is_category(self) -> bool: return isinstance(self.current, CategoryChannel)
    def is_forum(self) -> bool: return isinstance(self.current, ForumChannel)
    def is_stage(self) -> bool: return isinstance(self.current, StageChannel)
    def is_voice_channel(self) -> bool: return isinstance(self.current, VoiceChannel)
    def is_text_channel(self) -> bool: return isinstance(self.current, TextChannel)
    def is_thread(self) -> bool: return isinstance(self.current, Thread)
    def is_messageable(self) -> bool: return isinstance(self.current, Messageable)

    def to_dict(self) -> Dict[str, Any]:
        dump_handled_ids = []
        def quick_dump_compiler(source) -> Any:
            if isinstance(source, CacheEntry): return quick_dumb_dict_compiler(source)
            if type(source) is list or type(source) is tuple: return list(map(quick_dump_compiler, source))
            if hasattr(source, '__slots__'): return quick_dumb_dict_compiler(CacheEntry(current=source))
            # if type(source) is dict TODO
            return source
        def quick_dumb_dict_compiler(source: CacheEntry) -> Dict[str, Any]:
            if not hasattr(source.current, '__slots__'): raise Exception(f'cannot compile {type(source.current)}')

            target = {'__type': quick_dump_compiler(source.current.__class__.__name__)} # __type is a bit ugly I suppose
            if hasattr(source.current, 'id'):
                target['id'] = source.current.id
                target['id_b64'] = base64.b64encode(str(source.current.id).encode()).decode()

                if target['id_b64'] in dump_handled_ids:
                    return target
                dump_handled_ids.append(target['id_b64'])

            for attr in source.current.__slots__:
                if attr in ('id', 'guild'): continue # dont nest .guild
                if not hasattr(source.current, attr): continue
                target[attr] = quick_dump_compiler(getattr(source.current, attr))

            return target

        return quick_dumb_dict_compiler(self)


# class CachedReaction:
#     def __init__(self, reaction: Reaction, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.reaction = reaction
#
#     def __getattr__(self, attr):
#         if hasattr(self, attr): return super(attr)
#         return getattr(self.reaction, attr)
#
#     @property
#     def id(self) -> str:
#         return f'{self.message.id}:{self.reaction}'
#
#     def time_window(self) -> [datetime, datetime]:
#         pass

@dataclass
class Event:
    name: str
    dispatched_at: datetime
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]
    __slots__ = ("name", "dispatched_at", "args", "kwargs")

    @property
    def id(self) -> str:
        def arg_id(arg) -> str:
            entry = CacheEntry(current=arg).to_dict()
            return entry["id"] if "id" in entry else ""
        return (f':{self.dispatched_at.timestamp()}'
                f'{self.name}'
                f':{":".join(map(lambda arg: str(arg_id(arg)), self.args))}'
                f':{":".join(map(lambda pair: f"{pair[0]}={arg_id(pair[1])}", self.kwargs))}'
                )

    # def __repr__(self) -> str:
    #     value = ' '.join(f'{attr}={getattr(self, attr)!r}' for attr in self.__slots__)
    #     return f'<{self.__class__.__name__} {value}>'
    #
    # # From discord.py/_RawReprMixin
    # def dump_compile(self) -> str:
    #     def quick_dumb_compile(obj, path: Tuple[Any, ...] = ()) -> str:
    #         if len(path) == 1 and path[0] in ('args', 'kwargs'): return ", ".join(map(lambda element: quick_dumb_compile(element, path=(*path, obj)), obj))
    #         if len(path) > 2 or not hasattr(obj, '__slots__'): return repr(obj)
    #
    #         def compile_atr(attr) -> str:
    #             if not hasattr(obj, attr): return 'None'
    #             return quick_dumb_compile(getattr(obj, attr), path=(*path, attr))
    #
    #         value = ' '.join(f'{attr}={compile_atr(attr)!r}' for attr in obj.__slots__)
    #         return f'<{obj.__class__.__name__} {value}>'
    #
    #     return quick_dumb_compile(self)

# Note: run.py doesn't have a way of hooking into its caching mechanism (state.py), just implement it separately
# TODO: Can probably be a lot cleaner - but just to isolate the functionality for now to forward to a db at somepoint
class Cache(Generic[TObject]):

    def __init__(self, parent: Optional[Cache] = None, mirrors: Optional[Iterable[Cache]] = None):
        self.parent = parent
        self.mirrors = mirrors

    async def initialize(self):
        if self.mirrors:
            for mirror in self.mirrors: await mirror.initialize()

    @functools.cached_property
    def objects(self) -> Cache[Hashable]:
        return self if self.parent is None else self.parent.objects

    # TODO: Could use channel.type here
    @functools.cached_property
    def events(self) -> Cache[Event]: return self.objects.filter(lambda o: o.is_event())
    @functools.cached_property
    def users(self) -> Cache[User]: return self.objects.filter(lambda o: o.is_user())
    @functools.cached_property
    def members(self) -> Cache[Member]: return self.objects.filter(lambda o: o.is_member())
    @functools.cached_property
    def reactions(self) -> Cache[Reaction]: return self.messages.flat_map(lambda message: message.current.reactions)
    @functools.cached_property
    def messages(self) -> Cache[Message]: return self.objects.filter(lambda o: o.is_message())
    @functools.cached_property
    def guilds(self) -> Cache[Guild]: return self.objects.filter(lambda o: o.is_guild())
    @functools.cached_property
    def channels(self) -> Cache[GuildChannel]: return self.objects.filter(lambda o: o.is_channel())
    @functools.cached_property
    def categories(self) -> Cache[CategoryChannel]: return self.objects.filter(lambda o: o.is_category())
    @functools.cached_property
    def forums(self) -> Cache[ForumChannel]: return self.objects.filter(lambda o: o.is_forum())
    @functools.cached_property
    def stages(self) -> Cache[StageChannel]: return self.objects.filter(lambda o: o.is_stage())
    @functools.cached_property
    def voice_channels(self) -> Cache[VoiceChannel]: return self.objects.filter(lambda o: o.is_voice_channel())
    @functools.cached_property
    def text_channels(self) -> Cache[TextChannel]: return self.objects.filter(lambda o: o.is_text_channel())
    @functools.cached_property
    def threads(self) -> Cache[Thread]: return self.objects.filter(lambda o: o.is_thread())
    @functools.cached_property
    def messageables(self) -> Cache[Messageable]: return self.objects.filter(lambda o: o.is_messageable())

    def count(self) -> int:
        entries = self.entries()
        count = len(entries)
        if count <= 0: return count

        # TODO Could be moved elsewhere
        if entries[0].is_reaction(): # if anything other than reactions are in the current cache, this will not capture that
            return sum(map(lambda entry: entry.current.count, entries))

        return count
    def empty(self) -> bool:
        return self.count() <= 0

    def entries(self) -> List[CacheEntry[TObject]]: # todo iterable
        raise NotImplementedError
    def current(self) -> Iterable[TObject]: return map(lambda entry: entry.current, self.entries())

    async def push(self, object: TObject) -> None:
        if self.parent: return await self.parent.push(object)

        entry = CacheEntry(current=object)

        await self.push_entry(entry)
        if self.mirrors:
            for mirror in self.mirrors: await mirror.push_entry(entry)
    async def push_entry(self, entry: CacheEntry):
        raise NotImplementedError

    # Helper functions
    def get(self, **attrs: Any) -> Optional[TObject]:
        return get(self.current(), **attrs)
    def get_all(self, **attrs: Any) -> Cache[TObject]:
        return self.filter(lambda entry: get([entry.current], **attrs) is not None)
    def find(self, predicate: Callable[[TObject], bool]) -> Optional[TObject]:
        return find(predicate, self.current())

    # TODO ; These just temps
    def filter(self, predicate: Callable[[CacheEntry[TObject]], bool]) -> Cache[TObject]:
        class FilteredCache(Cache):
            def entries(self) -> List[CacheEntry[TObject]]:
                return list(filter(predicate, self.parent.entries()))

        return FilteredCache(parent=self)
    def map(self, func) -> Cache[TTarget]:
        class MappedCache(Cache):
            def entries(self) -> List[CacheEntry[TObject]]:
                return list(map(func, self.parent.entries()))

        return MappedCache(parent=self)
    def flat_map(self, func) -> Cache[TTarget]:
        class MappedCache(Cache):
            def entries(self) -> List[CacheEntry[TObject]]:
                return [CacheEntry(current=obj) for obj in chain.from_iterable(map(func, self.parent.entries()))]

        return MappedCache(parent=self)
    def group_by(self, func) -> Cache[TTarget]:
        class GroupByCache(Cache):
            def entries(self) -> List[CacheEntry[TTarget]]:
                # TODO: Values are now an iterable TObject, should be CacheEntry[TObject] use Cache(entries= ) for now
                return [CacheEntry(current=[CacheEntry(current=group), MemoryCache(entries=values)]) for group, values in groupby(self.parent.entries(), func)]
                # return map(lambda grouped_entry: [grouped_entry[0], Cache(entries=grouped_entry[1])], groupby(self.parent.entries(), func))

        return GroupByCache(parent=self)
    def sort(self, func) -> Cache[TTarget]:
        class SortedCache(Cache):
            def entries(self) -> List[CacheEntry[TObject]]:
                return sorted(self.parent.entries(), key=func)

        return SortedCache(parent=self)
    def first(self) -> Optional[CacheEntry[TObject]]: return None if self.empty() else self.entries()[0]
    def last(self) -> Optional[CacheEntry[TObject]]: return None if self.empty() else self.entries()[-1]

class MemoryCache(Cache):
    _entries: Deque[CacheEntry[TObject]] # TODO DOESNT WORK WITH MAP/FILTER YET

    def __init__(self, entries: Optional[Iterable[TObject]] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._entries = deque(entries or [])

    def entries(self) -> List[CacheEntry[TObject]]:
        return list(self._entries)
    async def push_entry(self, entry: CacheEntry):
        cached_entry = get(self.entries(), id=entry.id)
        if cached_entry is not None:
            cached_entry.current = entry.current # TODO; Now it's just last found, this will probably have to be different
            return

        self._entries.append(entry)
class GitCache(Cache):

    def __init__(self, repository: str, directory: str, branch: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.repository = repository
        self.directory = directory
        self.branch = branch

    async def clone(self):
        # note that it doesn't support dynamic changes to self.directory
        if not os.path.exists(self.directory): subprocess.run(["git", "clone", self.repository, self.directory])

        # Simple check to prevent local dev issues
        existing_repository = subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=self.directory, capture_output=True, text=True).stdout.rstrip()
        if existing_repository != self.repository: raise Exception(f'Found a repository at "{self.directory}" which does not match "{self.repository}": "{existing_repository}"')

        subprocess.run(["git", "fetch", "--all"], cwd=self.directory)
        subprocess.run(["git", "reset", "--hard", f'origin/{self.branch}'], cwd=self.directory)
    async def initialize(self):
        await self.clone()

    async def push_entry(self, entry: CacheEntry):
        obj = entry.to_dict()
        id = obj['id_b64']
        dir = (f'{self.directory}'
               f'/{obj["__type"]}'
               f'/{"/".join(wrap(id[:4], 2))}/{id[4:]}') # git-like object store

        def to_markdown(self) -> str: return self.to_obsidian()
        def to_obsidian(self) -> str:
            raise NotImplementedError
        def to_json() -> str:
            # https://stackoverflow.com/a/36142844/22730673
            return json.dumps(obj, indent=2, sort_keys=True, default=str)

        Path(dir).mkdir(parents=True, exist_ok=True)
        print(to_json(), file=open(f'{dir}/{id}.json', 'w'))
        print(f'{dir}/{id}.json')
        # raise NotImplementedError
        pass

def cached_event(func: Callable):
    @functools.wraps(func)
    async def method(self, *args, **kwargs):
        event = Event(name=func.__name__, dispatched_at=datetime.now(timezone.utc), args=args, kwargs=kwargs)

        await self.cache.events.push(event)
        return await func(self, *args, **kwargs)

    return method

def cached_traversal(cache: Callable[[Cache], Cache]):
    def decorator(func):
        @functools.wraps(func)
        async def method(self, entry, *args, **kwargs):
            await cache(self.cache).push(entry)
            return await func(self, entry, *args, **kwargs)

        return method

    return decorator

class DiscordTraverser(FunctionQueue):
    cache: Cache

    @dataclass
    class Options:
        before: Optional[datetime] = None,
        after: Optional[datetime] = None,

    def __init__(self, cache: Cache, options: Options = None):
        super().__init__()
        self.cache = cache
        self.options = options

    # @cached_traversal(lambda cache: cache.reactions)
    # async def push_reaction(self, reaction: Reaction):
        # await self.push(reaction.users())
        # pass
    @cached_traversal(lambda cache: cache.users)
    async def push_user(self, user: User):
        pass
    @cached_traversal(lambda cache: cache.members)
    async def push_member(self, member: Member):
        pass

    @cached_traversal(lambda cache: cache.messages)
    async def push_message(self, message: Message):
        # await self.push(message.reactions)
        # await self.push(message.author)
        pass

    @queue
    @cached_traversal(lambda cache: cache.messageables)
    async def push_messageable(self, channel: Messageable):
        await self.push(channel.history(
            before=self.options.before,
            after=self.options.after,
            around=None, oldest_first=False, limit=None
        ))

    @queue
    @cached_traversal(lambda cache: cache.threads)
    async def push_thread(self, thread: Thread):
        await self.push_messageable(thread)
    @queue
    @cached_traversal(lambda cache: cache.channels)
    async def push_channel(self, channel: GuildChannel):
        if isinstance(channel, Messageable): await self.push_messageable(channel)
        # TODO; now happens double for push_guild
        if isinstance(channel, ForumChannel) or isinstance(channel, TextChannel):
            await self.push(channel.threads)

            # Note: guild/channel.threads is only active (last 30ish days), also include older ones
            # TODO: This can probably also be achieved through 'push_message' by checking if it's a thread
            if isinstance(channel, ForumChannel):
                await self.push(channel.archived_threads(limit = None, before = self.options.before))
            if isinstance(channel, TextChannel):
                await self.push(channel.archived_threads(limit = None, before = self.options.before, joined = False, private = False))

    @queue
    @cached_traversal(lambda cache: cache.guilds)
    async def push_guild(self, guild: Guild):
        for channel in guild.channels: await self.push_channel(channel)
        # Note: This includes forum threads
        for thread in guild.threads: await self.push_thread(thread)

    @queue
    async def push_iterator(self, iterator: AsyncIterator):
        async for item in iterator: await self.push(item)

    async def push(self, source: Optional[Any]) -> None:
        # print(f'{type(source)}')
        if not source: return

        if isinstance(source, Messageable): await self.push_messageable(source); return
        if isinstance(source, Thread): await self.push_thread(source); return
        if isinstance(source, GuildChannel): await self.push_channel(source); return
        if isinstance(source, Message): await self.push_message(source); return
        if isinstance(source, Guild): await self.push_guild(source); return
        # if isinstance(source, Reaction): await self.push_reaction(source); return
        if isinstance(source, User): await self.push_user(source); return
        if isinstance(source, Member): await self.push_member(source); return

        if isinstance(source, AsyncIterator): await self.push_iterator(source); return
        if isinstance(source, Iterable):
            for item in source: await self.push(item)
            return

        raise NotImplementedError(type(source))
