from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Optional

from discord import Embed, Interaction
from discord.ext import commands
from discord.ext.commands.context import Context
import discord.utils

import humanize


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="t!", intents=intents)

# from https://discord.com/developers/docs/reference#message-formatting-timestamp-styles
TIME_FORMAT_TEMPLATES = {
    r"{:%H:%M}": "t",  # 16:20
    r"{:%d/%m/%Y}": "d",  # 20/04/2021
    r"{:%d %B %Y}": "D",  # 20 April 2021
    r"{:%d %B %Y %H:%M}": "f",  # 20 April 2021 16:20
    r"{:%A, %d %B %Y %H:%M}": "F",  # Tuesday, 20 April 2021 16:20
    # relative timestamps [e.g. 2 months ago] need to be added separately
    # since they can't use f-string date formatting after : so option must be added separately below
}


def console_log_with_time(msg: str):
    print(f'[timestamp] {datetime.now(tz=timezone.utc):%Y/%m/%d %H:%M:%S%z} - {msg}')


def create_relative_label(user_datetime: datetime) -> str:
    """Creates a human-readable relative time label similar to that used by Discord for user_datetime"""

    now = datetime.now(tz=timezone.utc)
    time_delta = now - user_datetime
    return humanize.naturaltime(time_delta)


def get_user_tag_from_origin(origin: Context | Interaction) -> str:
    """Build a user's tag from context for logging purposes"""

    if isinstance(origin, Context):
        user = origin.author

    elif isinstance(origin, Interaction):
        user = origin.user

    else:
        raise TypeError('argument discord_info must be a Context or Interaction object')

    return f'{user.name}#{user.discriminator}'


async def show_all_button_callback(interaction: Interaction, epoch_time):
    await send_all_timestamps_embed(interaction, epoch_time)


def show_all_button(time_obj: datetime) -> discord.ui.Button:
    """Create a Button component to trigger showing the all timestamps embed (created below)"""

    epoch_time = int(time_obj.timestamp())

    button = discord.ui.Button(
        label='Show All!',
        style=discord.ButtonStyle.primary,  # blurple style
        emoji=bot.get_emoji(816705774201077830),  # id of LLK Discord :wow: emoji
    )
    button.callback = lambda i: show_all_button_callback(i, epoch_time)

    return button


def timezone_guide_button() -> discord.ui.Button:
    return discord.ui.Button(
        label='Find out your timezone offset',
        emoji=discord.PartialEmoji(name='🕑'),
        style=discord.ButtonStyle.link,
        url='https://en.wikipedia.org/wiki/List_of_tz_database_time_zones'
    )


class TimestampDropdown(discord.ui.Select):
    def __init__(self, time_obj: datetime, utc_offset_used: bool):
        self.time_obj = time_obj
        self.utc_offset_used = utc_offset_used
        # convert *aware* datetime obj to (second-precise) unix epoch time
        self.epoch_time = int(self.time_obj.timestamp())

        options = []
        # Set the options that will be presented inside the dropdown
        # add all other options
        for template, format_key in TIME_FORMAT_TEMPLATES.items():
            options.append(discord.SelectOption(label=template.format(self.time_obj), value=format_key))
        # and relative option
        options.append(discord.SelectOption(label=f'{create_relative_label(self.time_obj)}', value='R'))

        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the three options
        # The options parameter defines the dropdown options. We defined this above
        super().__init__(placeholder='Or choose a specific format for your timestamp',
                         min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        user_format_choice = self.values[0]

        final_timestamp = f'<t:{self.epoch_time}:{user_format_choice}>'

        # build final embed for response to user
        timestamp_embed = Embed(
            title=f'For *__you__*, this timestamp will display as\n{final_timestamp}\n'
                  'It will be localised for everyone else! 🎉',
            description='***On mobile**, long press the date/time string above to copy the format code shown below.*\n'
                        f'\\{final_timestamp}',
        )

        if self.utc_offset_used:
            warning_msg = 'make sure your UTC offset (`±HHMM` *note no colon*) is correct. '
        else:
            warning_msg = 'make sure `HH:MM` is in UTC or you include a UTC offset (`±HHMM` *note no colon*) .'

        timestamp_embed.add_field(
            name='⚠',
            value='If the displayed timestamp looks wrong, ' + warning_msg,
        )

        resp_view = discord.ui.View()
        resp_view.add_item(show_all_button(self.time_obj))
        resp_view.add_item(timezone_guide_button())

        # using .respond() so only visible to triggering user (vs .send())
        console_log_with_time(f'Sent standard final timestamp embed to {get_user_tag_from_origin(interaction)}')
        await interaction.response.send_message(embed=timestamp_embed, view=resp_view, ephemeral=True)


async def send_all_timestamps_embed(interaction: Interaction, epoch_time: int) -> None:
    """Creates and sends an Embed with all possible Discord timestamps for epoch_time (in secs)"""

    response_embed = Embed(
        title='All the timestamp options!',
        description='Too much choice can only be a good thing, right?\n'
                    '***On mobile**, long press the date/time string to copy the format code shown below.*',
    )

    # don't forget to add relative back in to the list
    full_format_key_list = list(TIME_FORMAT_TEMPLATES.values()) + ['R']
    for format_key in full_format_key_list:
        discord_stamp = f'<t:{epoch_time}:{format_key}>'
        # adds each separate timestamp variation as a new inline field
        # \\ escapes timestamp so raw string is displayed in Discord
        response_embed.add_field(name=discord_stamp, value=f'\\{discord_stamp}', inline=True)

    console_log_with_time(f'Sent all timestamps embed to {get_user_tag_from_origin(interaction)}')
    await interaction.response.send_message(embed=response_embed, ephemeral=True)


async def send_success_response(repliable: Context | Interaction, time_obj: datetime, utc_offset_used: bool):
    resp_view = discord.ui.View()
    resp_view.add_item(show_all_button(time_obj))
    resp_view.add_item(TimestampDropdown(time_obj, utc_offset_used))

    reply_data = dict(
        content='Your date passed the reality test!\n'
                '*NB: The final numbers and format may differ slightly from those shown in the dropdown*',
        view=resp_view, ephemeral=True
    )
    if isinstance(repliable, Context):
        await repliable.reply(**reply_data)
    elif isinstance(repliable, Interaction):
        await repliable.response.send_message(**reply_data)

    console_log_with_time(f'Sent format selection embed in response to {get_user_tag_from_origin(repliable)}')


async def error_with_time_values(repliable: Context | Interaction):
    error_embed = Embed(
        title="That date didn't seem to work out :/",
        description='Make sure your input date+time is in the format '
                    '`YYYY/MM/DD HH:MM[±HHMM]` and is actually a date that exists!\n'
                    'e.g. `2021/08/21 22:05`, `2021/08/22 00:05+0200`, `2021/08/21 18:35-0330`\n'
                    "Don't forget: either `HH:MM` is in UTC "
                    "or you've included a UTC-offset, `±HHMM` (*note no colon*)!"
    )

    help_button_view = discord.ui.View()
    help_button_view.add_item(timezone_guide_button())

    reply_data = dict(embed=error_embed, view=help_button_view, ephemeral=True)
    if isinstance(repliable, Context):
        await repliable.reply(**reply_data)
    elif isinstance(repliable, Interaction):
        await repliable.response.send_message(**reply_data)

    console_log_with_time(f'Sent error embed in response to {get_user_tag_from_origin(repliable)}')


@bot.command(  # text used for help commands
    brief='Converts datetime to Discord timestamp. Also available as a slash command.',
    description="Use 't!mestamp YYYY/MM/DD HH:MM[±HHMM]' to convert datetime "
                "to a Discord usable timestamp in 1 of 6 formats.\n"
                "±HHMM (*note no colon*) is an optional UTC-offset. "
                "Use your local HH:MM together with your UTC offset or just UTC HH:MM with no offset.\n\n"
                "e.g. t!mestamp 2021/08/21 22:05 -> format number 5 selected -> <t:1629583500:F>\n"
                "(displayed in UTC+1 regions as 'Saturday, 21 August 2021 23:05')\n\n"
                "e.g. t!mestamp 2021/08/21 09:55+0100 -> format number 1 selected -> <t:1629536100:t> \n"
                "(displayed in UTC+1 regions as '09:55')"
)
# together with t! prefix, spells 't!mestamp' - the main bot command
async def mestamp(ctx: Context, *, user_datetime: str = ''):
    try:  # Assuming user_datetime includes a UTC offset (e.g. +0100)
        # creates an aware datetime obj since it includes a UTC offset (%z)
        time_obj = datetime.strptime(user_datetime.strip(), '%Y/%m/%d %H:%M%z')
        utc_offset_used = True
    except ValueError:  # i.e. user_datetime doesn't match the expected format
        try:  # maybe it didn't include a UTC offset?
            # in this case assume their time is UTC (no offset, %z) and create a naive datetime obj
            time_obj = datetime.strptime(user_datetime.strip(), '%Y/%m/%d %H:%M')
            time_obj = time_obj.replace(tzinfo=timezone.utc)  # make datetime obj aware by adding tzinfo
            utc_offset_used = False
        except ValueError:  # user_datetime didn't match either expected format :(
            await error_with_time_values(ctx)
            return  # exit function - no valid datetime entered

    # if we reached here and function wasn't exited - date must be valid!
    await send_success_response(ctx, time_obj, utc_offset_used)


@bot.tree.command(description='Converts a datetime to a Discord timestamp interactively in 1 of 6 formats.')
@discord.app_commands.describe(offset='UTC offset in format ±HHMM (*note no colon*)')
async def timestamp(interaction: Interaction,
                    year: int,
                    month: discord.app_commands.Range[int, 1, 12],
                    day: discord.app_commands.Range[int, 1, 31],
                    hour: discord.app_commands.Range[int, 0, 23],
                    minutes: discord.app_commands.Range[int, 0, 59],
                    offset: Optional[str] = ''):

    constructed_date_str = f'{year:04}/{month:02}/{day:02} {hour:02}:{minutes:02}'
    strp_str = '%Y/%m/%d %H:%M'
    if offset:
        utc_offset_used = True
        constructed_date_str += f'{offset}'
        strp_str += '%z'
    else:
        utc_offset_used = False

    try:
        time_obj = datetime.strptime(constructed_date_str, strp_str)
    except ValueError:
        await error_with_time_values(interaction)
        return

    if not utc_offset_used:
        time_obj = time_obj.replace(tzinfo=timezone.utc)

    await send_success_response(interaction, time_obj, utc_offset_used)


@bot.event  # initial start-up event
async def on_ready():
    await bot.change_presence(activity=discord.Game('type t!help mestamp to see help'))

    sync_guild = discord.Object(id=145229754390282240)
    bot.tree.copy_global_to(guild=sync_guild)
    # DEPLOY TODO: change guild to None for global sync
    await bot.tree.sync(guild=sync_guild)

    console_log_with_time('Timestamp Maker Bot is ready and raring to accept commands via Discord!')


# DEPLOY TODO: hardcode token
bot.run(os.environ['DISCORD_TIMESTAMP_TOKEN'])
