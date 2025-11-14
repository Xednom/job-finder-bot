# jobfinder_bot.py
import os
import logging
import aiohttp
import discord

from pathlib import Path
from typing import List, Dict, Any

from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from discord.ext import tasks

from db import init_db, mark_job_seen, get_all_saved_searches
from sources import (
    fetch_jobs_remotive,
    fetch_jobs_remoteok,
    fetch_jobs_rss,
    fetch_jobs_onlinejobs,
    fetch_jobs_weworkremotely,
    fetch_jobs_flexjobs,
    fetch_jobs_jobstreet,
    fetch_jobs_upwork,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jobfinder")

POLL_INTERVAL_MINUTES = 15  # how often to poll saved searches


def _load_dotenv_if_present(env_path: Path | str = ".env") -> None:
    """Try to load environment variables from a .env file.

    Prefer using python-dotenv when installed; fall back to a tiny parser if not.
    """
    envp = Path(env_path)
    if not envp.exists():
        return

    try:
        # prefer to use python-dotenv if available
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=envp, override=False)
        return
    except Exception:
        # if python-dotenv is not available, fall back to basic parsing
        try:
            with open(envp, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"')
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            # best-effort; don't crash here
            pass


_load_dotenv_if_present()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    # Provide actionable guidance rather than just failing silently
    raise RuntimeError(
        "Please set DISCORD_TOKEN environment variable."
        " You can put it into a .env file at the project root (see .env.example)"
        " or export DISCORD_TOKEN in your shell before running the bot."
    )

# --- Configuration ---
DEFAULT_SOURCE = "remotive"  # example free API
MAX_RESULTS = 10  # how many jobs to fetch and paginate
JOBS_PER_PAGE = 3


# Job fetchers are implemented in `sources.py` and imported above.


# Add other source functions here (RemoteOK, RSS, custom scrapers) as needed.


# --- Pagination View ---
class JobPaginationView(View):
    def __init__(
        self, jobs: List[Dict[str, Any]], author_id: int, timeout: float = 120.0
    ):
        super().__init__(timeout=timeout)
        self.jobs = jobs
        self.page = 0
        self.author_id = author_id

        # Buttons
        self.prev_btn = Button(label="◀️ Prev", style=discord.ButtonStyle.secondary)
        self.next_btn = Button(label="Next ▶️", style=discord.ButtonStyle.secondary)
        self.add_item(self.prev_btn)
        self.add_item(self.next_btn)

        self.prev_btn.callback = self.on_prev
        self.next_btn.callback = self.on_next
        self.update_buttons()

    def update_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = (self.page + 1) * JOBS_PER_PAGE >= max(
            1, len(self.jobs)
        )

    async def on_prev(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "You didn't run this search — buttons are locked to the requester.",
                ephemeral=True,
            )
            return
        self.page = max(0, self.page - 1)
        self.update_buttons()
        await interaction.response.edit_message(
            embed=build_jobs_embed(self.jobs, self.page), view=self
        )

    async def on_next(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "You didn't run this search — buttons are locked to the requester.",
                ephemeral=True,
            )
            return
        self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(
            embed=build_jobs_embed(self.jobs, self.page), view=self
        )

    async def on_timeout(self):
        # disable all buttons after timeout
        for child in self.children:
            child.disabled = True
        try:
            # edit message to disable buttons; this requires we stored the message
            # but discord automatically calls on_timeout; we do no-op here
            pass
        except Exception:
            pass


def build_jobs_embed(jobs: List[Dict[str, Any]], page: int) -> discord.Embed:
    start = page * JOBS_PER_PAGE
    end = start + JOBS_PER_PAGE
    slice_jobs = jobs[start:end]

    embed = discord.Embed(
        title="Job Search Results",
        description=f"Showing {start + 1}-{min(end, len(jobs))} of {len(jobs)} results",
        color=discord.Color.blurple(),
    )
    if not slice_jobs:
        embed.description = "No jobs found for your query."
        return embed

    for job in slice_jobs:
        title = job.get("title") or job.get("job_title") or "Untitled"
        company = (
            job.get("company_name")
            or job.get("company")
            or job.get("organization")
            or ""
        )
        url = job.get("url") or job.get("job_url") or job.get("url") or "No URL"
        location = (
            job.get("candidate_required_location")
            or job.get("location")
            or "Remote or unspecified"
        )
        salary = job.get("salary") or job.get("salary_range") or ""
        short_desc = job.get("description") or job.get("job_description") or ""
        # keep small - strip tags if needed
        short_desc = (short_desc[:200] + "...") if len(short_desc) > 200 else short_desc
        name_line = f"{title} — {company}" if company else title
        field_value = f"**Location:** {location}\n"
        if salary:
            field_value += f"**Salary:** {salary}\n"
        field_value += f"[Apply / Read more]({url})\n\n{short_desc}"
        embed.add_field(name=name_line, value=field_value, inline=False)

    embed.set_footer(
        text=f"Page {page + 1} / {max(1, (len(jobs) + JOBS_PER_PAGE - 1) // JOBS_PER_PAGE)}"
    )
    return embed


# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True  # Enable reading message content for text commands
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


@bot.event
async def on_ready():
    # initialize DB and background tasks on first ready
    try:
        await init_db()
    except Exception:
        logger.exception("Failed to initialize DB")

    if not poll_saved_searches.is_running():
        poll_saved_searches.start()

    logger.info(f"Logged in as {bot.user} (id: {bot.user.id})")
    try:
        synced = await tree.sync()
        logger.info(f"Synced {len(synced)} commands.")
    except Exception as e:
        logger.warning(f"Could not sync commands: {e}")


# --- Slash command ---
@tree.command(
    name="findjob",
    description="Find jobs (e.g. 'virtual assistant', 'data entry', etc.)",
)
@app_commands.describe(
    role="Job title or keywords",
    location="Preferred location (optional)",
    remote="Remote only?",
    source="Which job source to query",
    experience="For Upwork: experience level (entry/intermediate/expert)",
)
async def findjob(
    interaction: discord.Interaction,
    role: str,
    location: str | None = None,
    remote: bool = True,
    source: str | None = DEFAULT_SOURCE,
    experience: str | None = "entry",
):
    await interaction.response.defer(thinking=True)
    query = role.strip()
    
    # Map experience level to contractor_tier for Upwork
    contractor_tier = 1  # Default to entry level
    if experience:
        exp_lower = experience.lower()
        if exp_lower in ["intermediate", "inter", "2"]:
            contractor_tier = 2
        elif exp_lower in ["expert", "advanced", "3"]:
            contractor_tier = 3
    
    logger.info(
        f"User {interaction.user} searches for '{query}' source={source} location={location} remote={remote} experience={experience}"
    )

    async with aiohttp.ClientSession() as session:
        try:
            if source == "remotive":
                jobs = await fetch_jobs_remotive(
                    session,
                    query=query,
                    limit=MAX_RESULTS,
                    location=location,
                    remote_only=remote,
                )
                # If Remotive fails or returns nothing, try RemoteOK as fallback
                if not jobs:
                    logger.info(
                        f"Remotive returned no results, trying RemoteOK for '{query}'"
                    )
                    jobs = await fetch_jobs_remoteok(
                        session, query=query, limit=MAX_RESULTS
                    )
            elif source == "remoteok":
                jobs = await fetch_jobs_remoteok(
                    session, query=query, limit=MAX_RESULTS
                )
            elif source == "onlinejobs":
                jobs = await fetch_jobs_onlinejobs(
                    session, query=query, limit=MAX_RESULTS
                )
                # If OnlineJobs times out or fails, try RemoteOK as fallback
                if not jobs:
                    logger.info(
                        f"OnlineJobs.ph failed, trying RemoteOK for '{query}'"
                    )
                    jobs = await fetch_jobs_remoteok(
                        session, query=query, limit=MAX_RESULTS
                    )
            elif source == "weworkremotely":
                jobs = await fetch_jobs_weworkremotely(
                    session, query=query, limit=MAX_RESULTS
                )
            elif source == "flexjobs":
                jobs = await fetch_jobs_flexjobs(
                    session, query=query, limit=MAX_RESULTS
                )
            elif source == "jobstreet":
                jobs = await fetch_jobs_jobstreet(
                    session, query=query, limit=MAX_RESULTS
                )
            elif source == "upwork":
                jobs = await fetch_jobs_upwork(
                    session, query=query, limit=MAX_RESULTS, contractor_tier=contractor_tier
                )
            else:
                # fallback: try multiple sources in order
                jobs = await fetch_jobs_remotive(
                    session,
                    query=query,
                    limit=MAX_RESULTS,
                    location=location,
                    remote_only=remote,
                )
                if not jobs:
                    logger.info(f"Remotive failed, trying RemoteOK for '{query}'")
                    jobs = await fetch_jobs_remoteok(
                        session, query=query, limit=MAX_RESULTS
                    )
                if not jobs:
                    logger.info(f"RemoteOK failed, trying WeWorkRemotely for '{query}'")
                    jobs = await fetch_jobs_weworkremotely(
                        session, query=query, limit=MAX_RESULTS
                    )
                if not jobs:
                    logger.info(f"WeWorkRemotely failed, trying OnlineJobs.ph for '{query}'")
                    jobs = await fetch_jobs_onlinejobs(
                        session, query=query, limit=MAX_RESULTS
                    )
        except aiohttp.ClientResponseError as e:
            logger.error(f"API error for query '{query}': {e}")
            await interaction.followup.send(
                f"The job API is temporarily unavailable. Please try again in a moment.",
                ephemeral=True,
            )
            return
        except Exception as e:
            logger.exception("Error fetching jobs")
            await interaction.followup.send(
                f"An unexpected error occurred while searching jobs: {e}",
                ephemeral=True,
            )
            return

    if not jobs:
        await interaction.followup.send(
            f"No jobs found for `{query}` (source={source}). Try broader keywords.",
            ephemeral=False,
        )
        return

    # create embed + view (pagination)
    embed = build_jobs_embed(jobs, page=0)
    view = JobPaginationView(jobs=jobs, author_id=interaction.user.id)
    await interaction.followup.send(embed=embed, view=view)


# --- Legacy text command (optional) ---
@bot.command(name="findjob")
async def findjob_text(ctx: commands.Context, *, role: str):
    """Legacy text command: !findjob virtual assistant"""
    await ctx.send(
        "Use slash command `/findjob` for better options. Running a quick search..."
    )
    # Forward to the same logic as the slash command (simple)
    # `fake_interaction` previously created for forwarding slash-like logic; not used
    # For quickness, run a small fetch and post results
    async with aiohttp.ClientSession() as session:
        jobs = await fetch_jobs_remotive(session, query=role, limit=5)
    if not jobs:
        return await ctx.send(f"No jobs found for `{role}`.")
    embed = build_jobs_embed(jobs, page=0)
    view = JobPaginationView(jobs=jobs, author_id=ctx.author.id)
    await ctx.send(embed=embed, view=view)


@tasks.loop(minutes=POLL_INTERVAL_MINUTES)
async def poll_saved_searches():
    # fetch saved searches from DB using the new function
    searches = await get_all_saved_searches()

    if not searches:
        return

    async with aiohttp.ClientSession() as session:
        for s in searches:
            sid = s["id"]
            user_id = s["user_id"]
            query = s["query"]
            location = s["location"]
            remote_only = bool(s["remote_only"])
            source = s["source"] or "remotive"

            # choose fetcher
            try:
                if source == "remotive":
                    jobs = await fetch_jobs_remotive(
                        session,
                        query=query,
                        limit=10,
                        location=location,
                        remote_only=remote_only,
                    )
                elif source == "remoteok":
                    jobs = await fetch_jobs_remoteok(session, query=query, limit=10)
                elif source == "onlinejobs":
                    jobs = await fetch_jobs_onlinejobs(session, query=query, limit=10)
                elif source == "weworkremotely":
                    jobs = await fetch_jobs_weworkremotely(session, query=query, limit=10)
                elif source == "flexjobs":
                    jobs = await fetch_jobs_flexjobs(session, query=query, limit=10)
                elif source == "jobstreet":
                    jobs = await fetch_jobs_jobstreet(session, query=query, limit=10)
                elif source == "upwork":
                    # Default to entry level for background searches
                    jobs = await fetch_jobs_upwork(session, query=query, limit=10, contractor_tier=1)
                elif source.startswith("rss:"):
                    feed = source.split(":", 1)[1]
                    jobs = await fetch_jobs_rss(session, feed_url=feed, limit=10)
                else:
                    jobs = await fetch_jobs_remotive(
                        session,
                        query=query,
                        limit=10,
                        location=location,
                        remote_only=remote_only,
                    )
            except Exception as e:
                # log and continue
                print("Fetcher error for", source, e)
                continue

            # iterate jobs and DM user for ones not already seen
            for j in jobs:
                unique_id = (
                    j.get("unique_id")
                    or j["url"]
                    or (j["title"] + j.get("company", ""))
                )
                new = await mark_job_seen(sid, str(unique_id))
                if new:
                    # send DM
                    user = await bot.fetch_user(user_id)
                    if user:
                        embed = discord.Embed(
                            title=j.get("title") or "New job",
                            description=f"{j.get('company', '')}",
                            url=j.get("url"),
                        )
                        embed.add_field(
                            name="Location",
                            value=j.get("location") or "Remote/Unspecified",
                            inline=True,
                        )
                        embed.add_field(name="Source", value=source, inline=True)
                        embed.set_footer(text=f"Search: {query}")
                        try:
                            await user.send(embed=embed)
                        except Exception:
                            # user may have DMs disabled; ignore
                            pass


# --- Run bot ---
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
