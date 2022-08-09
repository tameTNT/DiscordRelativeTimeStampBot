from datetime import datetime, timezone
import os
from typing import Union

import keep_alive

from discord import Embed
from discord.errors import HTTPException
from discord.ext import commands
from discord.ext.commands.context import Context
from discord_components import DiscordComponents, Select, SelectOption, Button
from discord_components.interaction import Interaction
import discord.utils

import humanize


bot = commands.Bot(command_prefix="t!")

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


def create_relative_label(user_datetime: datetime) -> str:
    """Creates a human readable relative time label similar to that used by Discord for user_datetime"""
    
    now = datetime.now(timezone.utc)
    time_delta = now - user_datetime
    return humanize.naturaltime(time_delta)


def get_user_tag(discord_info: Union[Context, Interaction]) -> str:
    """Build a user's tag from context for logging purposes"""
    
    if isinstance(discord_info, Context):
        user = discord_info.author    

    elif isinstance(discord_info, Interaction):
        user = discord_info.user
    
    return f'{user.name}#{user.discriminator}'  # e.g. tameTNT#7902 <- me!


def create_show_all_button(epoch_time: int, utc_offset_used: int) -> Button:
    """Create a Button component to trigger showing the all timestamps embed (created below)"""

    return Button(
        label='Show All! (not useful on mobile)', 
        style='1',  # blurple style
        # embed information in custom_id (see SelectOption objs in main command)
        custom_id=f'show_all_button:{epoch_time},{utc_offset_used}',
        emoji=bot.get_emoji(816705774201077830),  # id of LLK Discord :wow: emoji
    )


async def send_all_timestamps_embed(epoch_time: int, interaction: Interaction) -> None:
    """Creates and sends an Embed with all possible Discord timestamps for epoch_time (in secs)"""

    response_embed = Embed(
        title='All the timestamp options!', 
        description='Too much choice can only be a good thing, right?'
    )
    
    # don't forget to add relative back in to the list
    full_format_key_list = list(TIME_FORMAT_TEMPLATES.values()) + ['R']
    for format_key in full_format_key_list:
        discord_stamp = f'<t:{epoch_time}:{format_key}>'
        # adds each seperate timestamp variation as a new inline field
        # \\ escapes timestamp so raw string is displayed in Discord
        response_embed.add_field(name=discord_stamp, value=f'\\{discord_stamp}', inline=True)
    
    
    print(f'{datetime.now()} - Sent all timestamps embed to {get_user_tag(interaction)}')
    await interaction.respond(embed=response_embed)


@bot.event  # initial start-up event
async def on_ready():
    DiscordComponents(bot)  # enables use of components argument in ctx.send() calls
    await bot.change_presence(activity=discord.Game('type t!help mestamp to see help'))
    print("Timestamp Maker Bot is ready and raring to accept commands via Discord!")

    # run a Flask server to allow for pinging from https://uptimerobot.com to keep repl.it running 
    # and awake it from periodic sleep
    # https://discordrelativetimestampbot.lucahuelle.repl.co/
    keep_alive.keep_alive()
    print('Bot and server both running')
    
   
@bot.command(  # text used for help commands
    brief="Converts datetime to Discord timestamp",
    description="Use 't!mestamp YYYY/MM/DD HH:MM[±HHMM]' to convert datetime to a Discord usable timestamp in 1 of 6 formats.\n"
                "±HHMM is an optional UTC-offset. Use your local HH:MM together with your UTC offset or just UTC HH:MM with no offset.\n\n"
                "e.g. t!mestamp 2021/08/21 22:05 -> format number 5 selected -> <t:1629583500:F>\n(displayed in UTC+1 regions as 'Saturday, 21 August 2021 23:05')\n\n"
                "e.g. t!mestamp 2021/08/21 09:55+0100 -> format number 1 selected -> \n(displayed in UTC+1 regions as '09:55')"
)
async def mestamp(ctx: Context, *, user_datetime: str=""):  # together with prefix, spells 't!mestamp' - the main bot cmd
    try:  # assuming user_datetime includes a UTC offset (e.g. +0100)
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
                title="Make sure input datetime is in the format:\n`YYYY/MM/DD HH:MM[±HHMM]`",
                description="e.g. `2021/08/21 22:05`, `2021/08/22 00:05+0200`, `2021/08/21 18:35-0330`\n"
                            "Don't forget: either `HH:MM` is in UTC or you've included a UTC-offset, `±HHMM`!"
            )
            print(f'{datetime.now()} - Sent error embed in response to {get_user_tag(ctx)}')
            await ctx.send(embed=error_embed)
            return  # exit function - no valid datetime entered

    # if we reached here and function wasn't exited - date must be valid!
    # convert *aware* datetime obj to (second-precise) unix epoch time
    epoch_time = int(time_obj.timestamp())

    # build the list of SelectOption component objs for the Select component obj later
    full_timestamp_options = []

    # add all other options
    for template, format_key in TIME_FORMAT_TEMPLATES.items():
        full_timestamp_options.append(SelectOption(label=template.format(time_obj), value=format_key))
    # and relative option
    full_timestamp_options.append(SelectOption(label=f"{create_relative_label(time_obj)}", value="R"))

    select_component = Select(
        placeholder="Choose a format for your timestamp",
        # custom_id constructed with f-string to pass data to on_select_option() function later on
        custom_id=f'timestamp_select:{epoch_time},{int(utc_offset_used)}',
        options=full_timestamp_options,
    )
    show_all_button = create_show_all_button(epoch_time, int(utc_offset_used))

    print(f'{datetime.now()} - Sent format selection embed in response to {get_user_tag(ctx)}')
    await ctx.send(
        content="Your date passed the reality test!\n"
                "*NB: The final numbers and format may differ slightly from those shown in the dropdown*",
        components=[select_component, show_all_button],
    )


@bot.event  # handles user selections from a Select obj components
async def on_select_option(interaction: Interaction):
    if interaction.parent_component.custom_id.startswith('timestamp_select'):
        # retrieve data from custom_id attribute set earlier (everything after : character)
        component_data = interaction.parent_component.custom_id.split(':')[1]
        epoch_time, utc_offset_used = map(int, component_data.split(','))  # convert both to int

        user_format_choice = interaction.component[0].value
        # option not used anymore - deprecated from:
        # full_timestamp_options.append(SelectOption(label='GIMME ALL OF THEM!', value="all"))
        if user_format_choice == 'all':
            await send_all_timestamps_embed(epoch_time, interaction)

        else:  # normal specific timestamp choice
            final_timestamp = f'<t:{epoch_time}:{user_format_choice}>'

            # build final embed for response to user
            timestamp_embed = Embed(
                    title=f"*For __you__, this timestamp will display as*\n*{final_timestamp}*\n"
                          "It will be localised for everyone else! 🎉",
                    description=f"\\{final_timestamp}", 
            )
            
            if utc_offset_used:
                warning_msg = "make sure your UTC offset (`±HHMM`) is correct. "
                warning_msg += "*You can check here: "\
                               "https://en.wikipedia.org/wiki/List_of_tz_database_time_zones*"
            else:
                warning_msg = "make sure `HH:MM` is in UTC or you include a UTC offset (`±HHMM`)."
            
            timestamp_embed.add_field(
                name='⚠', 
                value='If the displayed timestamp is wrong, ' + warning_msg,
            )

            show_all_button = create_show_all_button(epoch_time, utc_offset_used)

            # using .respond() so only visible to triggering user (vs .send())
            print(f'{datetime.now()} - Sent standard final timestamp embed to {get_user_tag(interaction)}')
            await interaction.respond(embed=timestamp_embed, components=[show_all_button])



@bot.event  # handles user interactions with Button obj components
async def on_button_click(interaction: Interaction):
    if interaction.component.custom_id.startswith('show_all_button'):
        # retrieve data from custom_id attribute (same as above)
        component_data = interaction.parent_component.custom_id.split(':')[1]
        epoch_time, offset_used = map(int, component_data.split(','))

        await send_all_timestamps_embed(epoch_time, interaction)


# actually run the bot using the Discord dev secret `DISCORD_TOKEN` set in repl.it Secrets panel
try:
    bot.run(os.environ['DISCORD_TOKEN'])
except HTTPException:
    print("HTTP ERROR 429 - Too Many Requests\nDiscord has rate limited repl.it and the bot will not work for this time.")
