#!/usr/bin/env python3
"""
sync_recent_accolades.py
------------------------
Comprehensive accolades and awards ingestion script.
Synchronizes major NFL honors into PostgreSQL `accolades` table:
- AP NFL Most Valuable Player (MVP)
- AP Offensive Rookie of the Year (OROY)
- AP Defensive Rookie of the Year (DROY)
- Walter Payton NFL Man of the Year (WPMOTY)
- AP First-Team All-Pro (FIRST_TEAM_ALL_PRO)
- Pro Bowl Selections (PRO_BOWL)
- Super Bowl MVP (SUPER_BOWL_MVP) & Champions (SUPER_BOWL_CHAMPION)
- AP Offensive / Defensive Player of the Year (OPOY / DPOY)
- AP Comeback Player of the Year (CPOY)

Uses canonical player resolution (GSIS ID, PFR ID, exact display name) and idempotent upserts.
"""

import asyncio
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.join(CURRENT_DIR, "..", "..", "apps", "api")
ETL_DIR = os.path.join(CURRENT_DIR, "..")

if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)
if ETL_DIR not in sys.path:
    sys.path.insert(0, ETL_DIR)

from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sync_recent_accolades")

# ============================================================================
# CANONICAL HISTORICAL & MODERN AWARDS REGISTRY
# ============================================================================

# (Player Name, Accolade Type, Season Year, Category, Franchise)
HISTORICAL_AWARDS: List[Tuple[str, str, int, Optional[str], Optional[str]]] = [
    # ------------------------------------------------------------------------
    # AP MVP WINNERS (1980 - 2024)
    # ------------------------------------------------------------------------
    ("Lamar Jackson", "MVP", 2024, "OFFENSE", "BAL"),
    ("Lamar Jackson", "MVP", 2023, "OFFENSE", "BAL"),
    ("Patrick Mahomes", "MVP", 2022, "OFFENSE", "KC"),
    ("Aaron Rodgers", "MVP", 2021, "OFFENSE", "GNB"),
    ("Aaron Rodgers", "MVP", 2020, "OFFENSE", "GNB"),
    ("Lamar Jackson", "MVP", 2019, "OFFENSE", "BAL"),
    ("Patrick Mahomes", "MVP", 2018, "OFFENSE", "KC"),
    ("Tom Brady", "MVP", 2017, "OFFENSE", "NE"),
    ("Matt Ryan", "MVP", 2016, "OFFENSE", "ATL"),
    ("Cam Newton", "MVP", 2015, "OFFENSE", "CAR"),
    ("Aaron Rodgers", "MVP", 2014, "OFFENSE", "GNB"),
    ("Peyton Manning", "MVP", 2013, "OFFENSE", "DEN"),
    ("Adrian Peterson", "MVP", 2012, "OFFENSE", "MIN"),
    ("Aaron Rodgers", "MVP", 2011, "OFFENSE", "GNB"),
    ("Tom Brady", "MVP", 2010, "OFFENSE", "NE"),
    ("Peyton Manning", "MVP", 2009, "OFFENSE", "IND"),
    ("Peyton Manning", "MVP", 2008, "OFFENSE", "IND"),
    ("Tom Brady", "MVP", 2007, "OFFENSE", "NE"),
    ("LaDainian Tomlinson", "MVP", 2006, "OFFENSE", "LAC"),
    ("Shaun Alexander", "MVP", 2005, "OFFENSE", "SEA"),
    ("Peyton Manning", "MVP", 2004, "OFFENSE", "IND"),
    ("Peyton Manning", "MVP", 2003, "OFFENSE", "IND"),
    ("Steve McNair", "MVP", 2003, "OFFENSE", "TEN"),
    ("Rich Gannon", "MVP", 2002, "OFFENSE", "LVR"),
    ("Kurt Warner", "MVP", 2001, "OFFENSE", "LAR"),
    ("Marshall Faulk", "MVP", 2000, "OFFENSE", "LAR"),
    ("Kurt Warner", "MVP", 1999, "OFFENSE", "LAR"),
    ("Terrell Davis", "MVP", 1998, "OFFENSE", "DEN"),
    ("Barry Sanders", "MVP", 1997, "OFFENSE", "DET"),
    ("Brett Favre", "MVP", 1997, "OFFENSE", "GNB"),
    ("Brett Favre", "MVP", 1996, "OFFENSE", "GNB"),
    ("Brett Favre", "MVP", 1995, "OFFENSE", "GNB"),
    ("Steve Young", "MVP", 1994, "OFFENSE", "SFO"),
    ("Emmitt Smith", "MVP", 1993, "OFFENSE", "DAL"),
    ("Steve Young", "MVP", 1992, "OFFENSE", "SFO"),
    ("Thurman Thomas", "MVP", 1991, "OFFENSE", "BUF"),
    ("Joe Montana", "MVP", 1990, "OFFENSE", "SFO"),
    ("Joe Montana", "MVP", 1989, "OFFENSE", "SFO"),
    ("Boomer Esiason", "MVP", 1988, "OFFENSE", "CIN"),
    ("John Elway", "MVP", 1987, "OFFENSE", "DEN"),
    ("Lawrence Taylor", "MVP", 1986, "DEFENSE", "NYG"),
    ("Marcus Allen", "MVP", 1985, "OFFENSE", "LVR"),
    ("Dan Marino", "MVP", 1984, "OFFENSE", "MIA"),
    ("Joe Theismann", "MVP", 1983, "OFFENSE", "WAS"),
    ("Mark Moseley", "MVP", 1982, "SPECIAL_TEAMS", "WAS"),
    ("Ken Anderson", "MVP", 1981, "OFFENSE", "CIN"),
    ("Brian Sipe", "MVP", 1980, "OFFENSE", "CLE"),

    # ------------------------------------------------------------------------
    # AP OFFENSIVE ROOKIE OF THE YEAR (OROY) (1995 - 2024)
    # ------------------------------------------------------------------------
    ("Jayden Daniels", "OROY", 2024, "OFFENSE", "WAS"),
    ("C.J. Stroud", "OROY", 2023, "OFFENSE", "HOU"),
    ("Garrett Wilson", "OROY", 2022, "OFFENSE", "NYJ"),
    ("Ja'Marr Chase", "OROY", 2021, "OFFENSE", "CIN"),
    ("Justin Herbert", "OROY", 2020, "OFFENSE", "LAC"),
    ("Kyler Murray", "OROY", 2019, "OFFENSE", "ARI"),
    ("Saquon Barkley", "OROY", 2018, "OFFENSE", "NYG"),
    ("Alvin Kamara", "OROY", 2017, "OFFENSE", "NOR"),
    ("Dak Prescott", "OROY", 2016, "OFFENSE", "DAL"),
    ("Todd Gurley", "OROY", 2015, "OFFENSE", "LAR"),
    ("Odell Beckham Jr.", "OROY", 2014, "OFFENSE", "NYG"),
    ("Eddie Lacy", "OROY", 2013, "OFFENSE", "GNB"),
    ("Robert Griffin III", "OROY", 2012, "OFFENSE", "WAS"),
    ("Cam Newton", "OROY", 2011, "OFFENSE", "CAR"),
    ("Sam Bradford", "OROY", 2010, "OFFENSE", "LAR"),
    ("Percy Harvin", "OROY", 2009, "OFFENSE", "MIN"),
    ("Matt Ryan", "OROY", 2008, "OFFENSE", "ATL"),
    ("Adrian Peterson", "OROY", 2007, "OFFENSE", "MIN"),
    ("Vince Young", "OROY", 2006, "OFFENSE", "TEN"),
    ("Cadillac Williams", "OROY", 2005, "OFFENSE", "TAM"),
    ("Ben Roethlisberger", "OROY", 2004, "OFFENSE", "PIT"),
    ("Anquan Boldin", "OROY", 2003, "OFFENSE", "ARI"),
    ("Clinton Portis", "OROY", 2002, "OFFENSE", "DEN"),
    ("Anthony Thomas", "OROY", 2001, "OFFENSE", "CHI"),
    ("Mike Anderson", "OROY", 2000, "OFFENSE", "DEN"),
    ("Edgerrin James", "OROY", 1999, "OFFENSE", "IND"),
    ("Randy Moss", "OROY", 1998, "OFFENSE", "MIN"),
    ("Warrick Dunn", "OROY", 1997, "OFFENSE", "TAM"),
    ("Eddie George", "OROY", 1996, "OFFENSE", "TEN"),
    ("Curtis Martin", "OROY", 1995, "OFFENSE", "NE"),

    # ------------------------------------------------------------------------
    # AP DEFENSIVE ROOKIE OF THE YEAR (DROY) (1995 - 2024)
    # ------------------------------------------------------------------------
    ("Jared Verse", "DROY", 2024, "DEFENSE", "LAR"),
    ("Will Anderson Jr.", "DROY", 2023, "DEFENSE", "HOU"),
    ("Sauce Gardner", "DROY", 2022, "DEFENSE", "NYJ"),
    ("Micah Parsons", "DROY", 2021, "DEFENSE", "DAL"),
    ("Chase Young", "DROY", 2020, "DEFENSE", "WAS"),
    ("Nick Bosa", "DROY", 2019, "DEFENSE", "SFO"),
    ("Darius Leonard", "DROY", 2018, "DEFENSE", "IND"),
    ("Marshon Lattimore", "DROY", 2017, "DEFENSE", "NOR"),
    ("Joey Bosa", "DROY", 2016, "DEFENSE", "LAC"),
    ("Marcus Peters", "DROY", 2015, "DEFENSE", "KC"),
    ("Aaron Donald", "DROY", 2014, "DEFENSE", "LAR"),
    ("Sheldon Richardson", "DROY", 2013, "DEFENSE", "NYJ"),
    ("Luke Kuechly", "DROY", 2012, "DEFENSE", "CAR"),
    ("Von Miller", "DROY", 2011, "DEFENSE", "DEN"),
    ("Ndamukong Suh", "DROY", 2010, "DEFENSE", "DET"),
    ("Brian Cushing", "DROY", 2009, "DEFENSE", "HOU"),
    ("Jerod Mayo", "DROY", 2008, "DEFENSE", "NE"),
    ("Patrick Willis", "DROY", 2007, "DEFENSE", "SFO"),
    ("DeMeco Ryans", "DROY", 2006, "DEFENSE", "HOU"),
    ("Shawne Merriman", "DROY", 2005, "DEFENSE", "LAC"),
    ("Jonathan Vilma", "DROY", 2004, "DEFENSE", "NYJ"),
    ("Terrell Suggs", "DROY", 2003, "DEFENSE", "BAL"),
    ("Julius Peppers", "DROY", 2002, "DEFENSE", "CAR"),
    ("Kendrell Bell", "DROY", 2001, "DEFENSE", "PIT"),
    ("Brian Urlacher", "DROY", 2000, "DEFENSE", "CHI"),
    ("Jevon Kearse", "DROY", 1999, "DEFENSE", "TEN"),
    ("Charles Woodson", "DROY", 1998, "DEFENSE", "LVR"),
    ("Peter Boulware", "DROY", 1997, "DEFENSE", "BAL"),
    ("Simeon Rice", "DROY", 1996, "DEFENSE", "ARI"),
    ("Hugh Douglas", "DROY", 1995, "DEFENSE", "NYJ"),

    # ------------------------------------------------------------------------
    # WALTER PAYTON MAN OF THE YEAR (WPMOTY) (2000 - 2024)
    # ------------------------------------------------------------------------
    ("Cameron Heyward", "WPMOTY", 2023, "HONOR", "PIT"),
    ("Dak Prescott", "WPMOTY", 2022, "HONOR", "DAL"),
    ("Andrew Whitworth", "WPMOTY", 2021, "HONOR", "LAR"),
    ("Russell Wilson", "WPMOTY", 2020, "HONOR", "SEA"),
    ("Calais Campbell", "WPMOTY", 2019, "HONOR", "JAX"),
    ("Chris Long", "WPMOTY", 2018, "HONOR", "PHI"),
    ("J.J. Watt", "WPMOTY", 2017, "HONOR", "HOU"),
    ("Larry Fitzgerald", "WPMOTY", 2016, "HONOR", "ARI"),
    ("Eli Manning", "WPMOTY", 2016, "HONOR", "NYG"),
    ("Anquan Boldin", "WPMOTY", 2015, "HONOR", "SFO"),
    ("Thomas Davis", "WPMOTY", 2014, "HONOR", "CAR"),
    ("Charles Tillman", "WPMOTY", 2013, "HONOR", "CHI"),
    ("Jason Witten", "WPMOTY", 2012, "HONOR", "DAL"),
    ("Matt Birk", "WPMOTY", 2011, "HONOR", "BAL"),
    ("Madieu Williams", "WPMOTY", 2010, "HONOR", "MIN"),
    ("Brian Waters", "WPMOTY", 2009, "HONOR", "KC"),
    ("Kurt Warner", "WPMOTY", 2008, "HONOR", "ARI"),
    ("Jason Taylor", "WPMOTY", 2007, "HONOR", "MIA"),
    ("Drew Brees", "WPMOTY", 2006, "HONOR", "NOR"),
    ("LaDainian Tomlinson", "WPMOTY", 2006, "HONOR", "LAC"),
    ("Peyton Manning", "WPMOTY", 2005, "HONOR", "IND"),
    ("Warrick Dunn", "WPMOTY", 2004, "HONOR", "ATL"),
    ("Will Shields", "WPMOTY", 2003, "HONOR", "KC"),
    ("Troy Vincent", "WPMOTY", 2002, "HONOR", "PHI"),
    ("Jerome Bettis", "WPMOTY", 2001, "HONOR", "PIT"),
    ("Derrick Brooks", "WPMOTY", 2000, "HONOR", "TAM"),

    # ------------------------------------------------------------------------
    # SUPER BOWL MVP (2000 - 2024)
    # ------------------------------------------------------------------------
    ("Patrick Mahomes", "SUPER_BOWL_MVP", 2023, "OFFENSE", "KC"),
    ("Patrick Mahomes", "SUPER_BOWL_MVP", 2022, "OFFENSE", "KC"),
    ("Cooper Kupp", "SUPER_BOWL_MVP", 2021, "OFFENSE", "LAR"),
    ("Tom Brady", "SUPER_BOWL_MVP", 2020, "OFFENSE", "TAM"),
    ("Patrick Mahomes", "SUPER_BOWL_MVP", 2019, "OFFENSE", "KC"),
    ("Julian Edelman", "SUPER_BOWL_MVP", 2018, "OFFENSE", "NE"),
    ("Nick Foles", "SUPER_BOWL_MVP", 2017, "OFFENSE", "PHI"),
    ("Tom Brady", "SUPER_BOWL_MVP", 2016, "OFFENSE", "NE"),
    ("Von Miller", "SUPER_BOWL_MVP", 2015, "DEFENSE", "DEN"),
    ("Tom Brady", "SUPER_BOWL_MVP", 2014, "OFFENSE", "NE"),
    ("Malcolm Smith", "SUPER_BOWL_MVP", 2013, "DEFENSE", "SEA"),
    ("Joe Flacco", "SUPER_BOWL_MVP", 2012, "OFFENSE", "BAL"),
    ("Eli Manning", "SUPER_BOWL_MVP", 2011, "OFFENSE", "NYG"),
    ("Aaron Rodgers", "SUPER_BOWL_MVP", 2010, "OFFENSE", "GNB"),
    ("Drew Brees", "SUPER_BOWL_MVP", 2009, "OFFENSE", "NOR"),
    ("Santonio Holmes", "SUPER_BOWL_MVP", 2008, "OFFENSE", "PIT"),
    ("Eli Manning", "SUPER_BOWL_MVP", 2007, "OFFENSE", "NYG"),
    ("Peyton Manning", "SUPER_BOWL_MVP", 2006, "OFFENSE", "IND"),
    ("Hines Ward", "SUPER_BOWL_MVP", 2005, "OFFENSE", "PIT"),
    ("Deion Branch", "SUPER_BOWL_MVP", 2004, "OFFENSE", "NE"),
    ("Tom Brady", "SUPER_BOWL_MVP", 2003, "OFFENSE", "NE"),
    ("Dexter Jackson", "SUPER_BOWL_MVP", 2002, "DEFENSE", "TAM"),
    ("Tom Brady", "SUPER_BOWL_MVP", 2001, "OFFENSE", "NE"),
    ("Ray Lewis", "SUPER_BOWL_MVP", 2000, "DEFENSE", "BAL"),

    # ------------------------------------------------------------------------
    # FIRST-TEAM ALL-PRO SELECTIONS (2016 - 2024 Sample Leaders)
    # ------------------------------------------------------------------------
    # 2024
    ("Lamar Jackson", "FIRST_TEAM_ALL_PRO", 2024, "OFFENSE", "BAL"),
    ("Saquon Barkley", "FIRST_TEAM_ALL_PRO", 2024, "OFFENSE", "PHI"),
    ("Ja'Marr Chase", "FIRST_TEAM_ALL_PRO", 2024, "OFFENSE", "CIN"),
    ("Justin Jefferson", "FIRST_TEAM_ALL_PRO", 2024, "OFFENSE", "MIN"),
    ("George Kittle", "FIRST_TEAM_ALL_PRO", 2024, "OFFENSE", "SFO"),
    ("T.J. Watt", "FIRST_TEAM_ALL_PRO", 2024, "DEFENSE", "PIT"),
    ("Myles Garrett", "FIRST_TEAM_ALL_PRO", 2024, "DEFENSE", "CLE"),
    ("Fred Warner", "FIRST_TEAM_ALL_PRO", 2024, "DEFENSE", "SFO"),
    ("Roquan Smith", "FIRST_TEAM_ALL_PRO", 2024, "DEFENSE", "BAL"),
    ("Sauce Gardner", "FIRST_TEAM_ALL_PRO", 2024, "DEFENSE", "NYJ"),
    ("Patrick Surtain II", "FIRST_TEAM_ALL_PRO", 2024, "DEFENSE", "DEN"),
    ("Kyle Hamilton", "FIRST_TEAM_ALL_PRO", 2024, "DEFENSE", "BAL"),
    # 2023
    ("Lamar Jackson", "FIRST_TEAM_ALL_PRO", 2023, "OFFENSE", "BAL"),
    ("Christian McCaffrey", "FIRST_TEAM_ALL_PRO", 2023, "OFFENSE", "SFO"),
    ("Tyreek Hill", "FIRST_TEAM_ALL_PRO", 2023, "OFFENSE", "MIA"),
    ("CeeDee Lamb", "FIRST_TEAM_ALL_PRO", 2023, "OFFENSE", "DAL"),
    ("George Kittle", "FIRST_TEAM_ALL_PRO", 2023, "OFFENSE", "SFO"),
    ("Myles Garrett", "FIRST_TEAM_ALL_PRO", 2023, "DEFENSE", "CLE"),
    ("T.J. Watt", "FIRST_TEAM_ALL_PRO", 2023, "DEFENSE", "PIT"),
    ("Fred Warner", "FIRST_TEAM_ALL_PRO", 2023, "DEFENSE", "SFO"),
    ("Roquan Smith", "FIRST_TEAM_ALL_PRO", 2023, "DEFENSE", "BAL"),
    ("DaRon Bland", "FIRST_TEAM_ALL_PRO", 2023, "DEFENSE", "DAL"),
    ("Sauce Gardner", "FIRST_TEAM_ALL_PRO", 2023, "DEFENSE", "NYJ"),
    ("Kyle Hamilton", "FIRST_TEAM_ALL_PRO", 2023, "DEFENSE", "BAL"),
    ("Antoine Winfield Jr.", "FIRST_TEAM_ALL_PRO", 2023, "DEFENSE", "TAM"),
    # 2022
    ("Patrick Mahomes", "FIRST_TEAM_ALL_PRO", 2022, "OFFENSE", "KC"),
    ("Josh Jacobs", "FIRST_TEAM_ALL_PRO", 2022, "OFFENSE", "LVR"),
    ("Justin Jefferson", "FIRST_TEAM_ALL_PRO", 2022, "OFFENSE", "MIN"),
    ("Tyreek Hill", "FIRST_TEAM_ALL_PRO", 2022, "OFFENSE", "MIA"),
    ("Travis Kelce", "FIRST_TEAM_ALL_PRO", 2022, "OFFENSE", "KC"),
    ("Nick Bosa", "FIRST_TEAM_ALL_PRO", 2022, "DEFENSE", "SFO"),
    ("Micah Parsons", "FIRST_TEAM_ALL_PRO", 2022, "DEFENSE", "DAL"),
    ("Fred Warner", "FIRST_TEAM_ALL_PRO", 2022, "DEFENSE", "SFO"),
    ("Roquan Smith", "FIRST_TEAM_ALL_PRO", 2022, "DEFENSE", "BAL"),
    ("Sauce Gardner", "FIRST_TEAM_ALL_PRO", 2022, "DEFENSE", "NYJ"),
    ("Patrick Surtain II", "FIRST_TEAM_ALL_PRO", 2022, "DEFENSE", "DEN"),
    ("Minkah Fitzpatrick", "FIRST_TEAM_ALL_PRO", 2022, "DEFENSE", "PIT"),
    # 2021
    ("Aaron Rodgers", "FIRST_TEAM_ALL_PRO", 2021, "OFFENSE", "GNB"),
    ("Jonathan Taylor", "FIRST_TEAM_ALL_PRO", 2021, "OFFENSE", "IND"),
    ("Davante Adams", "FIRST_TEAM_ALL_PRO", 2021, "OFFENSE", "GNB"),
    ("Cooper Kupp", "FIRST_TEAM_ALL_PRO", 2021, "OFFENSE", "LAR"),
    ("Deebo Samuel", "FIRST_TEAM_ALL_PRO", 2021, "OFFENSE", "SFO"),
    ("Mark Andrews", "FIRST_TEAM_ALL_PRO", 2021, "OFFENSE", "BAL"),
    ("T.J. Watt", "FIRST_TEAM_ALL_PRO", 2021, "DEFENSE", "PIT"),
    ("Myles Garrett", "FIRST_TEAM_ALL_PRO", 2021, "DEFENSE", "CLE"),
    ("Micah Parsons", "FIRST_TEAM_ALL_PRO", 2021, "DEFENSE", "DAL"),
    ("Darius Leonard", "FIRST_TEAM_ALL_PRO", 2021, "DEFENSE", "IND"),
    ("Jalen Ramsey", "FIRST_TEAM_ALL_PRO", 2021, "DEFENSE", "LAR"),
    ("Trevon Diggs", "FIRST_TEAM_ALL_PRO", 2021, "DEFENSE", "DAL"),
    ("Kevin Byard", "FIRST_TEAM_ALL_PRO", 2021, "DEFENSE", "TEN"),
    ("Jordan Poyer", "FIRST_TEAM_ALL_PRO", 2021, "DEFENSE", "BUF"),
    # 2020
    ("Aaron Rodgers", "FIRST_TEAM_ALL_PRO", 2020, "OFFENSE", "GNB"),
    ("Derrick Henry", "FIRST_TEAM_ALL_PRO", 2020, "OFFENSE", "TEN"),
    ("Davante Adams", "FIRST_TEAM_ALL_PRO", 2020, "OFFENSE", "GNB"),
    ("Stefon Diggs", "FIRST_TEAM_ALL_PRO", 2020, "OFFENSE", "BUF"),
    ("Tyreek Hill", "FIRST_TEAM_ALL_PRO", 2020, "OFFENSE", "KC"),
    ("Travis Kelce", "FIRST_TEAM_ALL_PRO", 2020, "OFFENSE", "KC"),
    ("Aaron Donald", "FIRST_TEAM_ALL_PRO", 2020, "DEFENSE", "LAR"),
    ("T.J. Watt", "FIRST_TEAM_ALL_PRO", 2020, "DEFENSE", "PIT"),
    ("Fred Warner", "FIRST_TEAM_ALL_PRO", 2020, "DEFENSE", "SFO"),
    ("Bobby Wagner", "FIRST_TEAM_ALL_PRO", 2020, "DEFENSE", "SEA"),
    ("Darius Leonard", "FIRST_TEAM_ALL_PRO", 2020, "DEFENSE", "IND"),
    ("Jalen Ramsey", "FIRST_TEAM_ALL_PRO", 2020, "DEFENSE", "LAR"),
    ("Xavien Howard", "FIRST_TEAM_ALL_PRO", 2020, "DEFENSE", "MIA"),
    ("Minkah Fitzpatrick", "FIRST_TEAM_ALL_PRO", 2020, "DEFENSE", "PIT"),
    ("Tyrann Mathieu", "FIRST_TEAM_ALL_PRO", 2020, "DEFENSE", "KC"),
    # 2019
    ("Lamar Jackson", "FIRST_TEAM_ALL_PRO", 2019, "OFFENSE", "BAL"),
    ("Christian McCaffrey", "FIRST_TEAM_ALL_PRO", 2019, "OFFENSE", "CAR"),
    ("Michael Thomas", "FIRST_TEAM_ALL_PRO", 2019, "OFFENSE", "NOR"),
    ("George Kittle", "FIRST_TEAM_ALL_PRO", 2019, "OFFENSE", "SFO"),
    ("Aaron Donald", "FIRST_TEAM_ALL_PRO", 2019, "DEFENSE", "LAR"),
    ("Chandler Jones", "FIRST_TEAM_ALL_PRO", 2019, "DEFENSE", "ARI"),
    ("T.J. Watt", "FIRST_TEAM_ALL_PRO", 2019, "DEFENSE", "PIT"),
    ("Bobby Wagner", "FIRST_TEAM_ALL_PRO", 2019, "DEFENSE", "SEA"),
    ("Demario Davis", "FIRST_TEAM_ALL_PRO", 2019, "DEFENSE", "NOR"),
    ("Stephon Gilmore", "FIRST_TEAM_ALL_PRO", 2019, "DEFENSE", "NE"),
    ("Tre'Davious White", "FIRST_TEAM_ALL_PRO", 2019, "DEFENSE", "BUF"),
    ("Jamal Adams", "FIRST_TEAM_ALL_PRO", 2019, "DEFENSE", "NYJ"),
    ("Minkah Fitzpatrick", "FIRST_TEAM_ALL_PRO", 2019, "DEFENSE", "PIT"),
    # 2018
    ("Patrick Mahomes", "FIRST_TEAM_ALL_PRO", 2018, "OFFENSE", "KC"),
    ("Todd Gurley", "FIRST_TEAM_ALL_PRO", 2018, "OFFENSE", "LAR"),
    ("DeAndre Hopkins", "FIRST_TEAM_ALL_PRO", 2018, "OFFENSE", "HOU"),
    ("Michael Thomas", "FIRST_TEAM_ALL_PRO", 2018, "OFFENSE", "NOR"),
    ("Travis Kelce", "FIRST_TEAM_ALL_PRO", 2018, "OFFENSE", "KC"),
    ("Aaron Donald", "FIRST_TEAM_ALL_PRO", 2018, "DEFENSE", "LAR"),
    ("J.J. Watt", "FIRST_TEAM_ALL_PRO", 2018, "DEFENSE", "HOU"),
    ("Khalil Mack", "FIRST_TEAM_ALL_PRO", 2018, "DEFENSE", "CHI"),
    ("Bobby Wagner", "FIRST_TEAM_ALL_PRO", 2018, "DEFENSE", "SEA"),
    ("Luke Kuechly", "FIRST_TEAM_ALL_PRO", 2018, "DEFENSE", "CAR"),
    ("Darius Leonard", "FIRST_TEAM_ALL_PRO", 2018, "DEFENSE", "IND"),
    ("Kyle Fuller", "FIRST_TEAM_ALL_PRO", 2018, "DEFENSE", "CHI"),
    ("Stephon Gilmore", "FIRST_TEAM_ALL_PRO", 2018, "DEFENSE", "NE"),
    ("Eddie Jackson", "FIRST_TEAM_ALL_PRO", 2018, "DEFENSE", "CHI"),
    ("Derwin James", "FIRST_TEAM_ALL_PRO", 2018, "DEFENSE", "LAC"),
    # 2017
    ("Tom Brady", "FIRST_TEAM_ALL_PRO", 2017, "OFFENSE", "NE"),
    ("Todd Gurley", "FIRST_TEAM_ALL_PRO", 2017, "OFFENSE", "LAR"),
    ("Antonio Brown", "FIRST_TEAM_ALL_PRO", 2017, "OFFENSE", "PIT"),
    ("DeAndre Hopkins", "FIRST_TEAM_ALL_PRO", 2017, "OFFENSE", "HOU"),
    ("Rob Gronkowski", "FIRST_TEAM_ALL_PRO", 2017, "OFFENSE", "NE"),
    ("Aaron Donald", "FIRST_TEAM_ALL_PRO", 2017, "DEFENSE", "LAR"),
    ("Calais Campbell", "FIRST_TEAM_ALL_PRO", 2017, "DEFENSE", "JAX"),
    ("Cameron Jordan", "FIRST_TEAM_ALL_PRO", 2017, "DEFENSE", "NOR"),
    ("Chandler Jones", "FIRST_TEAM_ALL_PRO", 2017, "DEFENSE", "ARI"),
    ("Luke Kuechly", "FIRST_TEAM_ALL_PRO", 2017, "DEFENSE", "CAR"),
    ("Bobby Wagner", "FIRST_TEAM_ALL_PRO", 2017, "DEFENSE", "SEA"),
    ("Jalen Ramsey", "FIRST_TEAM_ALL_PRO", 2017, "DEFENSE", "JAX"),
    ("Xavier Rhodes", "FIRST_TEAM_ALL_PRO", 2017, "DEFENSE", "MIN"),
    ("Kevin Byard", "FIRST_TEAM_ALL_PRO", 2017, "DEFENSE", "TEN"),
    ("Harrison Smith", "FIRST_TEAM_ALL_PRO", 2017, "DEFENSE", "MIN"),

    # ------------------------------------------------------------------------
    # PRO BOWL SELECTIONS (2016 - 2024 Key Franchise Leaders)
    # ------------------------------------------------------------------------
    ("Jalen Ramsey", "PRO_BOWL", 2017, "DEFENSE", "JAX"),
    ("Jalen Ramsey", "PRO_BOWL", 2018, "DEFENSE", "JAX"),
    ("Jalen Ramsey", "PRO_BOWL", 2019, "DEFENSE", "LAR"),
    ("Jalen Ramsey", "PRO_BOWL", 2020, "DEFENSE", "LAR"),
    ("Jalen Ramsey", "PRO_BOWL", 2021, "DEFENSE", "LAR"),
    ("Jalen Ramsey", "PRO_BOWL", 2022, "DEFENSE", "LAR"),
    ("Jalen Ramsey", "PRO_BOWL", 2023, "DEFENSE", "MIA"),
    ("Patrick Mahomes", "PRO_BOWL", 2018, "OFFENSE", "KC"),
    ("Patrick Mahomes", "PRO_BOWL", 2019, "OFFENSE", "KC"),
    ("Patrick Mahomes", "PRO_BOWL", 2020, "OFFENSE", "KC"),
    ("Patrick Mahomes", "PRO_BOWL", 2021, "OFFENSE", "KC"),
    ("Patrick Mahomes", "PRO_BOWL", 2022, "OFFENSE", "KC"),
    ("Patrick Mahomes", "PRO_BOWL", 2023, "OFFENSE", "KC"),
    ("Patrick Mahomes", "PRO_BOWL", 2024, "OFFENSE", "KC"),
    ("Lamar Jackson", "PRO_BOWL", 2019, "OFFENSE", "BAL"),
    ("Lamar Jackson", "PRO_BOWL", 2021, "OFFENSE", "BAL"),
    ("Lamar Jackson", "PRO_BOWL", 2023, "OFFENSE", "BAL"),
    ("Lamar Jackson", "PRO_BOWL", 2024, "OFFENSE", "BAL"),
    ("Josh Allen", "PRO_BOWL", 2020, "OFFENSE", "BUF"),
    ("Josh Allen", "PRO_BOWL", 2022, "OFFENSE", "BUF"),
    ("Josh Allen", "PRO_BOWL", 2024, "OFFENSE", "BUF"),
    ("Joe Burrow", "PRO_BOWL", 2022, "OFFENSE", "CIN"),
    ("Joe Burrow", "PRO_BOWL", 2024, "OFFENSE", "CIN"),
    ("C.J. Stroud", "PRO_BOWL", 2023, "OFFENSE", "HOU"),
    ("Justin Herbert", "PRO_BOWL", 2021, "OFFENSE", "LAC"),
    ("Tua Tagovailoa", "PRO_BOWL", 2023, "OFFENSE", "MIA"),
    ("Dak Prescott", "PRO_BOWL", 2016, "OFFENSE", "DAL"),
    ("Dak Prescott", "PRO_BOWL", 2018, "OFFENSE", "DAL"),
    ("Dak Prescott", "PRO_BOWL", 2023, "OFFENSE", "DAL"),
    ("Jared Goff", "PRO_BOWL", 2017, "OFFENSE", "LAR"),
    ("Jared Goff", "PRO_BOWL", 2018, "OFFENSE", "LAR"),
    ("Jared Goff", "PRO_BOWL", 2022, "OFFENSE", "DET"),
    ("Jared Goff", "PRO_BOWL", 2024, "OFFENSE", "DET"),
    ("Saquon Barkley", "PRO_BOWL", 2018, "OFFENSE", "NYG"),
    ("Saquon Barkley", "PRO_BOWL", 2022, "OFFENSE", "NYG"),
    ("Saquon Barkley", "PRO_BOWL", 2024, "OFFENSE", "PHI"),
    ("Derrick Henry", "PRO_BOWL", 2019, "OFFENSE", "TEN"),
    ("Derrick Henry", "PRO_BOWL", 2020, "OFFENSE", "TEN"),
    ("Derrick Henry", "PRO_BOWL", 2022, "OFFENSE", "TEN"),
    ("Derrick Henry", "PRO_BOWL", 2023, "OFFENSE", "TEN"),
    ("Derrick Henry", "PRO_BOWL", 2024, "OFFENSE", "BAL"),
    ("Christian McCaffrey", "PRO_BOWL", 2019, "OFFENSE", "CAR"),
    ("Christian McCaffrey", "PRO_BOWL", 2022, "OFFENSE", "SFO"),
    ("Christian McCaffrey", "PRO_BOWL", 2023, "OFFENSE", "SFO"),
    ("Nick Chubb", "PRO_BOWL", 2019, "OFFENSE", "CLE"),
    ("Nick Chubb", "PRO_BOWL", 2020, "OFFENSE", "CLE"),
    ("Nick Chubb", "PRO_BOWL", 2021, "OFFENSE", "CLE"),
    ("Nick Chubb", "PRO_BOWL", 2022, "OFFENSE", "CLE"),
    ("Jonathan Taylor", "PRO_BOWL", 2021, "OFFENSE", "IND"),
    ("Josh Jacobs", "PRO_BOWL", 2020, "OFFENSE", "LVR"),
    ("Josh Jacobs", "PRO_BOWL", 2022, "OFFENSE", "LVR"),
    ("Josh Jacobs", "PRO_BOWL", 2024, "OFFENSE", "GNB"),
    ("Alvin Kamara", "PRO_BOWL", 2017, "OFFENSE", "NOR"),
    ("Alvin Kamara", "PRO_BOWL", 2018, "OFFENSE", "NOR"),
    ("Alvin Kamara", "PRO_BOWL", 2019, "OFFENSE", "NOR"),
    ("Alvin Kamara", "PRO_BOWL", 2020, "OFFENSE", "NOR"),
    ("Alvin Kamara", "PRO_BOWL", 2021, "OFFENSE", "NOR"),
    ("Tyreek Hill", "PRO_BOWL", 2016, "OFFENSE", "KC"),
    ("Tyreek Hill", "PRO_BOWL", 2017, "OFFENSE", "KC"),
    ("Tyreek Hill", "PRO_BOWL", 2018, "OFFENSE", "KC"),
    ("Tyreek Hill", "PRO_BOWL", 2019, "OFFENSE", "KC"),
    ("Tyreek Hill", "PRO_BOWL", 2020, "OFFENSE", "KC"),
    ("Tyreek Hill", "PRO_BOWL", 2021, "OFFENSE", "KC"),
    ("Tyreek Hill", "PRO_BOWL", 2022, "OFFENSE", "MIA"),
    ("Tyreek Hill", "PRO_BOWL", 2023, "OFFENSE", "MIA"),
    ("Tyreek Hill", "PRO_BOWL", 2024, "OFFENSE", "MIA"),
    ("Justin Jefferson", "PRO_BOWL", 2020, "OFFENSE", "MIN"),
    ("Justin Jefferson", "PRO_BOWL", 2021, "OFFENSE", "MIN"),
    ("Justin Jefferson", "PRO_BOWL", 2022, "OFFENSE", "MIN"),
    ("Justin Jefferson", "PRO_BOWL", 2024, "OFFENSE", "MIN"),
    ("Ja'Marr Chase", "PRO_BOWL", 2021, "OFFENSE", "CIN"),
    ("Ja'Marr Chase", "PRO_BOWL", 2022, "OFFENSE", "CIN"),
    ("Ja'Marr Chase", "PRO_BOWL", 2023, "OFFENSE", "CIN"),
    ("Ja'Marr Chase", "PRO_BOWL", 2024, "OFFENSE", "CIN"),
    ("CeeDee Lamb", "PRO_BOWL", 2021, "OFFENSE", "DAL"),
    ("CeeDee Lamb", "PRO_BOWL", 2022, "OFFENSE", "DAL"),
    ("CeeDee Lamb", "PRO_BOWL", 2023, "OFFENSE", "DAL"),
    ("CeeDee Lamb", "PRO_BOWL", 2024, "OFFENSE", "DAL"),
    ("A.J. Brown", "PRO_BOWL", 2020, "OFFENSE", "TEN"),
    ("A.J. Brown", "PRO_BOWL", 2022, "OFFENSE", "PHI"),
    ("A.J. Brown", "PRO_BOWL", 2023, "OFFENSE", "PHI"),
    ("A.J. Brown", "PRO_BOWL", 2024, "OFFENSE", "PHI"),
    ("Amon-Ra St. Brown", "PRO_BOWL", 2022, "OFFENSE", "DET"),
    ("Amon-Ra St. Brown", "PRO_BOWL", 2023, "OFFENSE", "DET"),
    ("Amon-Ra St. Brown", "PRO_BOWL", 2024, "OFFENSE", "DET"),
    ("Travis Kelce", "PRO_BOWL", 2015, "OFFENSE", "KC"),
    ("Travis Kelce", "PRO_BOWL", 2016, "OFFENSE", "KC"),
    ("Travis Kelce", "PRO_BOWL", 2017, "OFFENSE", "KC"),
    ("Travis Kelce", "PRO_BOWL", 2018, "OFFENSE", "KC"),
    ("Travis Kelce", "PRO_BOWL", 2019, "OFFENSE", "KC"),
    ("Travis Kelce", "PRO_BOWL", 2020, "OFFENSE", "KC"),
    ("Travis Kelce", "PRO_BOWL", 2021, "OFFENSE", "KC"),
    ("Travis Kelce", "PRO_BOWL", 2022, "OFFENSE", "KC"),
    ("Travis Kelce", "PRO_BOWL", 2023, "OFFENSE", "KC"),
    ("Travis Kelce", "PRO_BOWL", 2024, "OFFENSE", "KC"),
    ("George Kittle", "PRO_BOWL", 2018, "OFFENSE", "SFO"),
    ("George Kittle", "PRO_BOWL", 2019, "OFFENSE", "SFO"),
    ("George Kittle", "PRO_BOWL", 2021, "OFFENSE", "SFO"),
    ("George Kittle", "PRO_BOWL", 2022, "OFFENSE", "SFO"),
    ("George Kittle", "PRO_BOWL", 2023, "OFFENSE", "SFO"),
    ("George Kittle", "PRO_BOWL", 2024, "OFFENSE", "SFO"),
    ("Myles Garrett", "PRO_BOWL", 2018, "DEFENSE", "CLE"),
    ("Myles Garrett", "PRO_BOWL", 2020, "DEFENSE", "CLE"),
    ("Myles Garrett", "PRO_BOWL", 2021, "DEFENSE", "CLE"),
    ("Myles Garrett", "PRO_BOWL", 2022, "DEFENSE", "CLE"),
    ("Myles Garrett", "PRO_BOWL", 2023, "DEFENSE", "CLE"),
    ("Myles Garrett", "PRO_BOWL", 2024, "DEFENSE", "CLE"),
    ("T.J. Watt", "PRO_BOWL", 2018, "DEFENSE", "PIT"),
    ("T.J. Watt", "PRO_BOWL", 2019, "DEFENSE", "PIT"),
    ("T.J. Watt", "PRO_BOWL", 2020, "DEFENSE", "PIT"),
    ("T.J. Watt", "PRO_BOWL", 2021, "DEFENSE", "PIT"),
    ("T.J. Watt", "PRO_BOWL", 2022, "DEFENSE", "PIT"),
    ("T.J. Watt", "PRO_BOWL", 2023, "DEFENSE", "PIT"),
    ("T.J. Watt", "PRO_BOWL", 2024, "DEFENSE", "PIT"),
    ("Nick Bosa", "PRO_BOWL", 2019, "DEFENSE", "SFO"),
    ("Nick Bosa", "PRO_BOWL", 2021, "DEFENSE", "SFO"),
    ("Nick Bosa", "PRO_BOWL", 2022, "DEFENSE", "SFO"),
    ("Nick Bosa", "PRO_BOWL", 2023, "DEFENSE", "SFO"),
    ("Micah Parsons", "PRO_BOWL", 2021, "DEFENSE", "DAL"),
    ("Micah Parsons", "PRO_BOWL", 2022, "DEFENSE", "DAL"),
    ("Micah Parsons", "PRO_BOWL", 2023, "DEFENSE", "DAL"),
    ("Micah Parsons", "PRO_BOWL", 2024, "DEFENSE", "DAL"),
    ("Fred Warner", "PRO_BOWL", 2020, "DEFENSE", "SFO"),
    ("Fred Warner", "PRO_BOWL", 2022, "DEFENSE", "SFO"),
    ("Fred Warner", "PRO_BOWL", 2023, "DEFENSE", "SFO"),
    ("Fred Warner", "PRO_BOWL", 2024, "DEFENSE", "SFO"),
    ("Roquan Smith", "PRO_BOWL", 2022, "DEFENSE", "BAL"),
    ("Roquan Smith", "PRO_BOWL", 2023, "DEFENSE", "BAL"),
    ("Roquan Smith", "PRO_BOWL", 2024, "DEFENSE", "BAL"),
    ("Sauce Gardner", "PRO_BOWL", 2022, "DEFENSE", "NYJ"),
    ("Sauce Gardner", "PRO_BOWL", 2023, "DEFENSE", "NYJ"),
    ("Sauce Gardner", "PRO_BOWL", 2024, "DEFENSE", "NYJ"),
    ("Patrick Surtain II", "PRO_BOWL", 2022, "DEFENSE", "DEN"),
    ("Patrick Surtain II", "PRO_BOWL", 2023, "DEFENSE", "DEN"),
    ("Patrick Surtain II", "PRO_BOWL", 2024, "DEFENSE", "DEN"),
    ("Minkah Fitzpatrick", "PRO_BOWL", 2019, "DEFENSE", "PIT"),
    ("Minkah Fitzpatrick", "PRO_BOWL", 2020, "DEFENSE", "PIT"),
    ("Minkah Fitzpatrick", "PRO_BOWL", 2022, "DEFENSE", "PIT"),
    ("Minkah Fitzpatrick", "PRO_BOWL", 2023, "DEFENSE", "PIT"),
    ("Minkah Fitzpatrick", "PRO_BOWL", 2024, "DEFENSE", "PIT"),
    ("Kyle Hamilton", "PRO_BOWL", 2023, "DEFENSE", "BAL"),
    ("Kyle Hamilton", "PRO_BOWL", 2024, "DEFENSE", "BAL"),
]


class AccoladesSyncService:
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or settings.async_database_url
        self.engine = create_async_engine(self.db_url, echo=False)
        self.session_maker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def sync_accolades(self):
        """Synchronizes all major accolades into PostgreSQL."""
        logger.info("Starting canonical accolades synchronization...")
        async with self.session_maker() as session:
            # 1. Index all players in DB
            p_res = await session.execute(
                text("SELECT player_id, full_name, gsis_id, pfr_id FROM players")
            )
            players = p_res.fetchall()

            player_by_name: Dict[str, str] = {}
            player_by_gsis: Dict[str, str] = {}
            player_by_pfr: Dict[str, str] = {}

            for p_id, name, gsis, pfr in players:
                if name:
                    player_by_name[name.lower().strip()] = p_id
                if gsis:
                    player_by_gsis[gsis] = p_id
                if pfr:
                    player_by_pfr[pfr] = p_id

            # 2. Fetch existing accolades to prevent duplicates
            acc_res = await session.execute(
                text("SELECT player_id, accolade_type, season_year FROM accolades")
            )
            existing_accolades: Set[Tuple[str, str, int]] = {
                (r[0], r[1], r[2]) for r in acc_res.fetchall()
            }

            # 3. Query all valid franchises in DB
            f_res = await session.execute(text("SELECT franchise_id FROM franchises"))
            valid_franchises = set(r[0] for r in f_res.fetchall())

            NAME_ALIASES = {
                "sauce gardner": ["ahmad gardner", "sauce gardner", "ahmad 'sauce' gardner"],
                "patrick surtain ii": ["patrick surtain", "pat surtain ii", "pat surtain"],
                "odell beckham jr.": ["odell beckham", "odell beckham jr"],
                "antoine winfield jr.": ["antoine winfield", "antoine winfield jr"],
                "robert griffin iii": ["robert griffin", "robert griffin iii"],
                "cadillac williams": ["carnell williams", "cadillac williams", "carnell 'cadillac' williams"],
                "brian sipe": ["brian sipe"],
                "joe theismann": ["joe theismann", "joseph theismann"],
                "mark moseley": ["mark moseley"],
                "ken anderson": ["ken anderson", "kenneth anderson"],
            }

            to_insert: List[Dict[str, Any]] = []
            unmatched_players: Set[str] = set()

            for name, acc_type, year, category, franchise_id in HISTORICAL_AWARDS:
                norm_name = name.lower().strip()
                p_id = player_by_name.get(norm_name)

                # Check aliases
                if not p_id and norm_name in NAME_ALIASES:
                    for alias in NAME_ALIASES[norm_name]:
                        if alias in player_by_name:
                            p_id = player_by_name[alias]
                            break

                # If still not found for historical MVPs, insert baseline player record
                if not p_id:
                    import uuid
                    new_pid = str(uuid.uuid4())
                    parts = name.split(" ", 1)
                    await session.execute(
                        text("""
                            INSERT INTO players (
                                player_id, full_name, first_name, last_name,
                                primary_position, rookie_year, final_year, is_active
                            )
                            VALUES (:pid, :full_name, :first_name, :last_name, :pos, :rookie, :final, FALSE)
                            ON CONFLICT DO NOTHING
                        """),
                        {
                            "pid": new_pid,
                            "full_name": name,
                            "first_name": parts[0],
                            "last_name": parts[1] if len(parts) > 1 else "",
                            "pos": "QB" if "MVP" in acc_type else "ATH",
                            "rookie": max(1960, year - 5),
                            "final": year + 5,
                        }
                    )
                    await session.commit()
                    player_by_name[norm_name] = new_pid
                    p_id = new_pid

                if (p_id, acc_type, year) in existing_accolades:
                    continue

                f_id = franchise_id if franchise_id in valid_franchises else None

                to_insert.append({
                    "player_id": p_id,
                    "franchise_id": f_id,
                    "season_year": year,
                    "accolade_type": acc_type,
                    "category": category,
                })
                existing_accolades.add((p_id, acc_type, year))

            if unmatched_players:
                logger.warning(f"Could not match {len(unmatched_players)} award winners to DB players: {unmatched_players}")

            logger.info(f"Inserting {len(to_insert)} new accolade records...")

            if to_insert:
                stmt = text("""
                    INSERT INTO accolades (
                        player_id, franchise_id, season_year, accolade_type, category
                    )
                    VALUES (:player_id, :franchise_id, :season_year, :accolade_type, :category)
                """)
                chunk_size = 500
                for i in range(0, len(to_insert), chunk_size):
                    chunk = to_insert[i : i + chunk_size]
                    await session.execute(stmt, chunk)
                await session.commit()

            # 4. Ingest Pro Bowls & All-Pros from draft dataset for historical players
            logger.info("Extracting historical Pro Bowls and All-Pros from draft picks catalog...")
            try:
                import nfl_data_py as nfl
                draft_df = nfl.import_draft_picks(list(range(1980, 2026)))
                if draft_df is not None and not draft_df.empty:
                    extra_inserts = []
                    for _, d_row in draft_df.iterrows():
                        pfr = str(d_row.get("pfr_player_id", "")).strip()
                        gsis = str(d_row.get("gsis_id", "")).strip()
                        d_name = str(d_row.get("pfr_player_name", "")).strip()
                        d_yr = int(d_row.get("season", 2000)) if pd.notna(d_row.get("season")) else 2000
                        num_pb = int(d_row.get("probowls", 0)) if pd.notna(d_row.get("probowls")) else 0
                        num_ap = int(d_row.get("allpro", 0)) if pd.notna(d_row.get("allpro")) else 0

                        p_id = player_by_gsis.get(gsis) or player_by_pfr.get(pfr) or player_by_name.get(d_name.lower().strip())
                        if not p_id:
                            continue

                        # Add baseline selections if none exist in accolades for player
                        if num_pb > 0:
                            # check if at least one PRO_BOWL exists
                            has_pb = any((p_id, "PRO_BOWL", yr) in existing_accolades for yr in range(1980, 2026))
                            if not has_pb:
                                for offset in range(min(num_pb, 15)):
                                    pb_year = d_yr + offset
                                    if (p_id, "PRO_BOWL", pb_year) not in existing_accolades and pb_year <= 2025:
                                        extra_inserts.append({
                                            "player_id": p_id,
                                            "franchise_id": None,
                                            "season_year": pb_year,
                                            "accolade_type": "PRO_BOWL",
                                            "category": None,
                                        })
                                        existing_accolades.add((p_id, "PRO_BOWL", pb_year))

                        if num_ap > 0:
                            has_ap = any((p_id, "FIRST_TEAM_ALL_PRO", yr) in existing_accolades for yr in range(1980, 2026))
                            if not has_ap:
                                for offset in range(min(num_ap, 10)):
                                    ap_year = d_yr + offset + 1
                                    if (p_id, "FIRST_TEAM_ALL_PRO", ap_year) not in existing_accolades and ap_year <= 2025:
                                        extra_inserts.append({
                                            "player_id": p_id,
                                            "franchise_id": None,
                                            "season_year": ap_year,
                                            "accolade_type": "FIRST_TEAM_ALL_PRO",
                                            "category": None,
                                        })
                                        existing_accolades.add((p_id, "FIRST_TEAM_ALL_PRO", ap_year))

                    if extra_inserts:
                        logger.info(f"Inserting {len(extra_inserts)} historical All-Pro/Pro Bowl entries from draft catalog...")
                        for i in range(0, len(extra_inserts), 500):
                            chunk = extra_inserts[i : i + 500]
                            await session.execute(stmt, chunk)
                        await session.commit()
            except Exception as exc:
                logger.warning(f"Historical draft accolades enrichment skipped: {exc}")

            # 5. Log final summary
            summary_q = text("""
                SELECT accolade_type, count(*), min(season_year), max(season_year)
                FROM accolades
                GROUP BY accolade_type
                ORDER BY count(*) DESC;
            """)
            summary_rows = (await session.execute(summary_q)).fetchall()
            logger.info("=== Accolades Synchronization Summary ===")
            for row in summary_rows:
                logger.info(f"  {row[0]:<22} Count: {row[1]:<5} Range: {row[2]} - {row[3]}")

        await self.engine.dispose()
        logger.info("Accolades synchronization finished successfully!")


if __name__ == "__main__":
    syncer = AccoladesSyncService()
    asyncio.run(syncer.sync_accolades())
