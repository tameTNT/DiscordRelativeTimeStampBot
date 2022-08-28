from datetime import datetime, timezone
import os
from typing import Union

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
    print(f'{datetime.now(tz=timezone.utc):%Y/%m/%d %H:%M:%S%z} - {msg}')


def create_relative_label(user_datetime: datetime) -> str:
    """Creates a human-readable relative time label similar to that used by Discord for user_datetime"""

    now = datetime.now(timezone.utc)
    time_delta = now - user_datetime
    return humanize.naturaltime(time_delta)


def get_user_tag(discord_info: Union[Context, Interaction]) -> str:
    """Build a user's tag from context for logging purposes"""

    if isinstance(discord_info, Context):
        user = discord_info.author

    elif isinstance(discord_info, Interaction):
        user = discord_info.user

    else:
        raise TypeError('argument discord_info must be a Context or Interaction object')

    return f'{user.name}#{user.discriminator}'


async def show_all_button_callback(interaction: Interaction, epoch_time):
    await send_all_timestamps_embed(interaction, epoch_time)


def create_show_all_button_view(time_obj: datetime) -> discord.ui.View:
    """Create a Button component to trigger showing the all timestamps embed (created below)"""

    epoch_time = int(time_obj.timestamp())

    show_all_button = discord.ui.Button(
        label='Show All!',
        style=discord.ButtonStyle.primary,  # blurple style
        emoji=bot.get_emoji(816705774201077830),  # id of LLK Discord :wow: emoji
    )
    show_all_button.callback = lambda i: show_all_button_callback(i, epoch_time)

    show_all_view = discord.ui.View()
    show_all_view.add_item(show_all_button)

    return show_all_view


def make_timezone_link_button() -> discord.ui.Button:
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
            options.append(discord.SelectOption(label=template.format(time_obj), value=format_key))
        # and relative option
        options.append(discord.SelectOption(label=f'{create_relative_label(time_obj)}', value='R'))

        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the three options
        # The options parameter defines the dropdown options. We defined this above
        super().__init__(placeholder='Or choose a specific format for your timestamp', min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        user_format_choice = self.values[0]

        if user_format_choice == 'all':
            await send_all_timestamps_embed(interaction, self.epoch_time)

        else:  # normal specific timestamp choice
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

            show_all_view = create_show_all_button_view(self.time_obj)
            show_all_view.add_item(make_timezone_link_button())

            # using .respond() so only visible to triggering user (vs .send())
            console_log_with_time(f'Sent standard final timestamp embed to {get_user_tag(interaction)}')
            await interaction.response.send_message(embed=timestamp_embed, view=show_all_view, ephemeral=True)


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

    console_log_with_time(f'Sent all timestamps embed to {get_user_tag(interaction)}')
    await interaction.response.send_message(embed=response_embed, ephemeral=True)


@bot.command(  # text used for help commands
    brief='Converts datetime to Discord timestamp',
    description="Use 't!mestamp YYYY/MM/DD HH:MM[±HHMM]' to convert datetime to a Discord usable timestamp in 1 of 6 formats.\n"
                "±HHMM (*note no colon*) is an optional UTC-offset. Use your local HH:MM together with your UTC offset or just UTC HH:MM with no offset.\n\n"
                "e.g. t!mestamp 2021/08/21 22:05 -> format number 5 selected -> <t:1629583500:F>\n(displayed in UTC+1 regions as 'Saturday, 21 August 2021 23:05')\n\n"
                "e.g. t!mestamp 2021/08/21 09:55+0100 -> format number 1 selected -> <t:1629536100:t> \n(displayed in UTC+1 regions as '09:55')"
)
async def mestamp(ctx: Context, *, user_datetime: str = ''):  # together with prefix, spells 't!mestamp' - the main bot cmd
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
            error_embed = Embed(
                title='Make sure input datetime is in the format:\n`YYYY/MM/DD HH:MM[±HHMM]`',
                description='e.g. `2021/08/21 22:05`, `2021/08/22 00:05+0200`, `2021/08/21 18:35-0330`\n'
                            "Don't forget: either `HH:MM` is in UTC or you've included a UTC-offset, `±HHMM` (*note no colon*)!"
            )
            console_log_with_time(f'Sent error embed in response to {get_user_tag(ctx)}')
            help_button_view = discord.ui.View()
            help_button_view.add_item(make_timezone_link_button())
            await ctx.reply(embed=error_embed, view=help_button_view, ephemeral=True)
            return  # exit function - no valid datetime entered

    # if we reached here and function wasn't exited - date must be valid!
    response_view = create_show_all_button_view(time_obj)
    response_view.add_item(TimestampDropdown(time_obj, utc_offset_used))

    console_log_with_time(f'Sent format selection embed in response to {get_user_tag(ctx)}')
    await ctx.reply(
        content="Your date passed the reality test!\n"
                "*NB: The final numbers and format may differ slightly from those shown in the dropdown*",
        view=response_view, ephemeral=True
    )


@bot.event  # initial start-up event
async def on_ready():
    await bot.change_presence(activity=discord.Game('type t!help mestamp to see help'))
    console_log_with_time('Timestamp Maker Bot is ready and raring to accept commands via Discord!')


bot.run(os.environ['DISCORD_TIMESTAMP_TOKEN'])
