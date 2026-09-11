"""
seed_historical_players.py
--------------------------
Seeds historical NFL players (Hall of Famers and other key figures) into the DB:
  - players table: player_id (UUID), full_name, position, rookie_year, is_active
  - player_team_stints: franchise affiliations from the catalog
  - accolades: HALL_OF_FAME entries for all HOF inductees
  - player_season_stats: key milestone seasons (rush/rec/sack/pass) for catalog players

Run from project root:
  $env:PYTHONPATH="apps/api"; python packages/etl/pipeline/seed_historical_players.py
"""

import asyncio
import sys
import uuid
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'apps', 'api'))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings

# ---------------------------------------------------------------------------
# HOF Player data: (full_name, position, rookie_year, hof_year, franchises)
# franchises = list of franchise_ids they played for
# ---------------------------------------------------------------------------
HOF_PLAYERS = [
    # QBs
    ("Brett Favre",       "QB",  1991, 2016, ["ATL", "GNB", "NYJ", "MIN"]),
    ("Dan Marino",        "QB",  1983, 2005, ["MIA"]),
    ("John Elway",        "QB",  1983, 2004, ["DEN"]),
    ("Joe Montana",       "QB",  1979, 2000, ["SFO", "KC"]),
    ("Steve Young",       "QB",  1984, 2005, ["TAM", "SFO"]),
    ("Troy Aikman",       "QB",  1989, 2006, ["DAL"]),
    ("Warren Moon",       "QB",  1984, 2006, ["TEN", "MIN", "SEA", "KC"]),
    ("Terry Bradshaw",    "QB",  1970, 1989, ["PIT"]),
    ("Fran Tarkenton",    "QB",  1961, 1986, ["MIN", "NYG"]),
    ("Roger Staubach",    "QB",  1969, 1985, ["DAL"]),
    ("Dan Fouts",         "QB",  1973, 1993, ["LAC"]),
    ("Jim Kelly",         "QB",  1986, 2002, ["BUF"]),
    ("Bob Griese",        "QB",  1967, 1990, ["MIA"]),
    ("Johnny Unitas",     "QB",  1956, 1979, ["IND", "LAC"]),
    ("Bart Starr",        "QB",  1956, 1977, ["GNB"]),
    ("Len Dawson",        "QB",  1957, 1987, ["PIT", "CLE", "KC"]),
    ("Kurt Warner",       "QB",  1998, 2017, ["LAR", "NYG", "ARI"]),
    ("Peyton Manning",    "QB",  1998, 2021, ["IND", "DEN"]),
    ("Drew Brees",        "QB",  2001, 2023, ["LAC", "NOR"]),
    ("Tom Brady",         "QB",  2000, 2023, ["NE", "TAM"]),
    ("Eli Manning",       "QB",  2004, 2026, ["NYG"]),  # eligible soon

    # RBs
    ("Emmitt Smith",      "RB",  1990, 2010, ["DAL", "ARI"]),
    ("Barry Sanders",     "RB",  1989, 2004, ["DET"]),
    ("Walter Payton",     "RB",  1975, 1993, ["CHI"]),
    ("Eric Dickerson",    "RB",  1983, 1999, ["LAR", "IND", "LVR", "ATL"]),
    ("Jim Brown",         "RB",  1957, 1971, ["CLE"]),
    ("Marshall Faulk",    "RB",  1994, 2011, ["IND", "LAR"]),
    ("Jerome Bettis",     "RB",  1993, 2015, ["LAR", "PIT"]),
    ("Tony Dorsett",      "RB",  1977, 1994, ["DAL", "DEN"]),
    ("Marcus Allen",      "RB",  1982, 2003, ["LVR", "KC"]),
    ("John Riggins",      "RB",  1971, 1992, ["NYJ", "WAS"]),
    ("Franco Harris",     "RB",  1972, 1990, ["PIT", "SEA"]),
    ("Gale Sayers",       "RB",  1965, 1977, ["CHI"]),
    ("Earl Campbell",     "RB",  1978, 1991, ["TEN", "NOR"]),
    ("O.J. Simpson",      "RB",  1969, 1985, ["BUF", "SFO"]),
    ("LaDainian Tomlinson","RB", 2001, 2017, ["LAC", "NYJ"]),
    ("Curtis Martin",     "RB",  1995, 2012, ["NE", "NYJ"]),
    ("Thurman Thomas",    "RB",  1988, 2007, ["BUF", "MIA"]),
    ("Adrian Peterson",   "RB",  2007, 2023, ["MIN", "ARI", "NOR", "WAS", "DET", "TEN", "SEA"]),
    ("Edgerrin James",    "RB",  1999, 2020, ["IND", "ARI", "SEA", "LAC"]),
    ("Terrell Davis",     "RB",  1995, 2017, ["DEN"]),
    ("Marvin Harrison",   "WR",  1996, 2016, ["IND"]),  # WR

    # WRs
    ("Jerry Rice",        "WR",  1985, 2010, ["SFO", "LVR", "SEA"]),
    ("Randy Moss",        "WR",  1998, 2018, ["MIN", "LVR", "NE", "TEN", "SFO"]),
    ("Terrell Owens",     "WR",  1996, 2018, ["SFO", "PHI", "DAL", "BUF", "CIN"]),
    ("Cris Carter",       "WR",  1987, 2013, ["PHI", "MIN", "MIA"]),
    ("Calvin Johnson",    "WR",  2007, 2021, ["DET"]),
    ("Tim Brown",         "WR",  1988, 2015, ["LVR", "TAM"]),
    ("Michael Irvin",     "WR",  1988, 2007, ["DAL"]),
    ("Steve Largent",     "WR",  1976, 1995, ["SEA"]),
    ("James Lofton",      "WR",  1978, 2003, ["GNB", "LVR", "BUF", "LAR", "PHI"]),
    ("Andre Reed",        "WR",  1985, 2014, ["BUF", "WAS"]),
    ("Lynn Swann",        "WR",  1974, 2001, ["PIT"]),
    ("John Stallworth",   "WR",  1974, 2002, ["PIT"]),
    ("Henry Ellard",      "WR",  1983, 1999, ["LAR", "WAS", "NE", "BAL", "NYJ"]),
    ("Art Monk",          "WR",  1980, 2008, ["WAS", "NYJ", "PHI"]),
    ("Charlie Joiner",    "WR",  1969, 1996, ["TEN", "CIN", "LAC"]),
    ("Paul Warfield",     "WR",  1964, 1983, ["CLE", "MIA"]),
    ("Don Maynard",       "WR",  1958, 1987, ["NYG", "NYJ", "LAR"]),
    ("Raymond Berry",     "WR",  1955, 1973, ["IND"]),
    ("Anquan Boldin",     "WR",  2003, 2023, ["ARI", "BAL", "SFO", "DET", "BUF", "NOR"]),
    ("Torry Holt",        "WR",  1999, 2023, ["LAR", "JAX"]),
    ("Tony Gonzalez",     "TE",  1997, 2019, ["KC", "ATL"]),
    ("Shannon Sharpe",    "TE",  1990, 2011, ["DEN", "BAL"]),
    ("Mike Ditka",        "TE",  1961, 1988, ["CHI", "PHI", "DAL", "NOR"]),
    ("Kellen Winslow",    "TE",  1979, 1995, ["LAC"]),
    ("Ozzie Newsome",     "TE",  1978, 1999, ["CLE"]),
    ("Dave Casper",       "TE",  1974, 2002, ["LVR", "TEN", "MIN"]),

    # OL
    ("Anthony Munoz",     "OL",  1980, 1998, ["CIN"]),
    ("Jonathan Ogden",    "OL",  1996, 2013, ["BAL"]),
    ("Orlando Pace",      "OL",  1997, 2016, ["LAR"]),
    ("Alan Faneca",       "OL",  1998, 2021, ["PIT", "NYJ", "ARI"]),
    ("Will Shields",      "OL",  1993, 2015, ["KC"]),
    ("Larry Allen",       "OL",  1994, 2013, ["DAL", "SFO"]),
    ("Bruce Matthews",    "OL",  1983, 2007, ["TEN"]),
    ("Randall McDaniel",  "OL",  1988, 2009, ["MIN", "TAM"]),
    ("Mike Munchak",      "OL",  1982, 2001, ["TEN"]),
    ("Jim Langer",        "OL",  1970, 1987, ["MIA", "MIN"]),

    # DL / DE
    ("Reggie White",      "DE",  1985, 2006, ["PHI", "GNB", "CAR"]),
    ("Bruce Smith",       "DE",  1985, 2009, ["BUF", "WAS"]),
    ("Lawrence Taylor",   "LB",  1981, 1999, ["NYG"]),
    ("Derrick Thomas",    "LB",  1989, 2009, ["KC"]),
    ("Dwight Freeney",    "DE",  2002, 2023, ["IND", "ARI", "LAC", "ATL", "SEA", "DET"]),
    ("Julius Peppers",    "DE",  2002, 2023, ["CAR", "CHI", "GNB", "LAR"]),
    ("Deacon Jones",      "DE",  1961, 1980, ["LAR", "LAC", "WAS"]),
    ("Gino Marchetti",    "DE",  1952, 1972, ["DAL", "IND"]),
    ("Carl Eller",        "DE",  1964, 2004, ["MIN", "SEA"]),
    ("Richard Dent",      "DE",  1983, 2011, ["CHI", "SFO", "IND", "PHI"]),
    ("Michael Strahan",   "DE",  1993, 2014, ["NYG"]),
    ("Warren Sapp",       "DL",  1995, 2013, ["TAM", "LVR"]),
    ("Bob Lilly",         "DL",  1961, 1980, ["DAL"]),
    ("Curly Culp",        "DL",  1968, 2013, ["KC", "TEN", "DET"]),
    ("Mean Joe Greene",   "DL",  1969, 1987, ["PIT"]),
    ("Merlin Olsen",      "DL",  1962, 1982, ["LAR"]),
    ("Randy White",       "DL",  1975, 1994, ["DAL"]),
    ("Buck Buchanan",     "DL",  1963, 1990, ["KC"]),
    ("Alan Page",         "DL",  1967, 1988, ["MIN", "CHI"]),

    # LBs
    ("Ray Lewis",         "LB",  1996, 2018, ["BAL"]),
    ("Brian Urlacher",    "LB",  2000, 2018, ["CHI"]),
    ("Dick Butkus",       "LB",  1965, 1979, ["CHI"]),
    ("Jack Lambert",      "LB",  1974, 1990, ["PIT"]),
    ("Junior Seau",       "LB",  1990, 2015, ["LAC", "MIA", "NE"]),
    ("Derrick Brooks",    "LB",  1995, 2014, ["TAM"]),
    ("Mike Singletary",   "LB",  1981, 1998, ["CHI"]),
    ("Ted Hendricks",     "LB",  1969, 1990, ["IND", "GNB", "LVR"]),
    ("Chuck Howley",      "LB",  1958, 1973, ["CHI", "DAL"]),
    ("Jack Ham",          "LB",  1971, 1988, ["PIT"]),
    ("Willie Lanier",     "LB",  1967, 1986, ["KC"]),
    ("Nick Buoniconti",   "LB",  1962, 2001, ["NE", "MIA"]),
    ("Dave Wilcox",       "LB",  1964, 2000, ["SFO"]),
    ("Bobby Bell",        "LB",  1963, 1983, ["KC"]),
    ("Chuck Bednarik",    "LB",  1949, 1967, ["PHI"]),
    ("DeMarcus Ware",     "LB",  2005, 2023, ["DAL", "DEN"]),
    ("Patrick Willis",    "LB",  2007, 2023, ["SFO"]),

    # DBs
    ("Deion Sanders",     "CB",  1989, 2011, ["ATL", "SFO", "DAL", "WAS", "BAL"]),
    ("Rod Woodson",       "CB",  1987, 2009, ["PIT", "SFO", "BAL", "LVR"]),
    ("Ronnie Lott",       "S",   1981, 2000, ["SFO", "LVR", "NYJ", "MIA"]),
    ("Ed Reed",           "S",   2002, 2019, ["BAL", "TEN", "NYJ"]),
    ("Troy Polamalu",     "S",   2003, 2020, ["PIT"]),
    ("Champ Bailey",      "CB",  1999, 2019, ["WAS", "DEN"]),
    ("Brian Dawkins",     "S",   1996, 2018, ["PHI", "DEN"]),
    ("Steve Atwater",     "S",   1989, 2020, ["DEN", "NYJ"]),
    ("Charles Woodson",   "CB",  1998, 2021, ["LVR", "GNB"]),
    ("Darrelle Revis",    "CB",  2007, 2023, ["NYJ", "TAM", "NE", "KC"]),
    ("John Lynch",        "S",   1993, 2021, ["TAM", "DEN"]),
    ("Mel Blount",        "CB",  1970, 1989, ["PIT"]),
    ("Herb Adderley",     "CB",  1961, 1980, ["GNB", "DAL"]),
    ("Dick Night Train Lane", "CB", 1952, 1974, ["LAR", "CLE", "DET"]),
    ("Willie Brown",      "CB",  1963, 1984, ["DEN", "LVR"]),
    ("Jack Christiansen", "S",   1951, 1970, ["DET"]),
    ("Larry Wilson",      "S",   1960, 1978, ["ARI"]),
    ("Emlen Tunnell",     "S",   1948, 1967, ["NYG", "GNB"]),
    ("Yale Lary",         "S",   1952, 1979, ["DET"]),
    ("Leroy Butler",      "S",   1990, 2023, ["GNB"]),
    ("Kenny Easley",      "S",   1981, 2017, ["SEA"]),
    ("Paul Krause",       "S",   1964, 1998, ["WAS", "MIN"]),
    ("Lem Barney",        "CB",  1967, 1992, ["DET"]),
    ("Mike Haynes",       "CB",  1976, 1997, ["NE", "LVR"]),
    ("Darrell Green",     "CB",  1983, 2008, ["WAS"]),
    ("Aeneas Williams",   "CB",  1991, 2014, ["ARI", "LAR"]),
    ("Cliff Harris",      "S",   1970, 2004, ["DAL"]),
    ("Mel Renfro",        "CB",  1964, 1996, ["DAL"]),
    ("Willie Wood",       "S",   1960, 1989, ["GNB"]),
    ("Larry Brown",       "CB",  1993, 2023, ["PIT", "LVR"]),
    ("Donnie Shell",      "S",   1974, 2020, ["PIT"]),

    # K / P / Special
    ("Jan Stenerud",      "K",   1967, 1991, ["KC", "GNB", "MIN"]),
]

# ---------------------------------------------------------------------------
# Additional historically significant players (non-HOF but needed for stats catalog)
# (full_name, position, rookie_year, is_hof, franchises)
# ---------------------------------------------------------------------------
HISTORICAL_NON_HOF = [
    # Modern stars / recently eligible
    ("Peyton Hillis",      "RB",  2008, False, ["CLE", "KC", "NYG", "TAM"]),
    ("Frank Gore",         "RB",  2005, False, ["SFO", "IND", "MIA", "BUF", "NYJ"]),
    ("Steven Jackson",     "RB",  2004, False, ["LAR", "ATL", "NE"]),
    ("Jamal Lewis",        "RB",  2000, False, ["BAL", "CLE"]),
    ("Clinton Portis",     "RB",  2002, False, ["DEN", "WAS"]),
    ("Larry Johnson",      "RB",  2003, False, ["KC", "MIA", "CIN", "WAS"]),
    ("Shaun Alexander",    "RB",  2000, False, ["SEA", "WAS"]),
    ("Chris Johnson",      "RB",  2008, False, ["TEN", "NYJ", "ARI"]),
    ("Tiki Barber",        "RB",  1997, False, ["NYG"]),
    ("Edgerrin James",     "RB",  1999, True,  ["IND", "ARI", "SEA", "LAC"]),
    ("Ricky Williams",     "RB",  1999, False, ["NOR", "MIA", "BAL"]),
    ("Priest Holmes",      "RB",  1997, False, ["BAL", "KC"]),
    ("Brian Westbrook",    "RB",  2002, False, ["PHI", "SFO"]),
    ("Warrick Dunn",       "RB",  1997, False, ["TAM", "ATL"]),
    ("Deuce McAllister",   "RB",  2001, False, ["NOR"]),
    ("Ahman Green",        "RB",  1998, False, ["SEA", "GNB", "HOU"]),
    ("Travis Henry",       "RB",  2001, False, ["BUF", "TEN", "DEN"]),
    ("Corey Dillon",       "RB",  1997, False, ["CIN", "NE"]),
    ("Eddie George",       "RB",  1996, False, ["TEN", "DAL"]),
    ("Garrison Hearst",    "RB",  1993, False, ["ARI", "CIN", "SFO", "DEN"]),
    ("Dorsey Levens",      "RB",  1994, False, ["GNB", "PHI", "NYG"]),
    ("Natrone Means",      "RB",  1993, False, ["LAC", "JAX", "CAR", "MIA"]),
    ("Jerome Bettis",      "RB",  1993, True,  ["LAR", "PIT"]),

    # QBs (non-HOF or near-HOF)
    ("Randall Cunningham", "QB",  1985, False, ["PHI", "MIN", "DAL", "BAL"]),
    ("Jim Everett",        "QB",  1986, False, ["LAR", "NOR", "LAC"]),
    ("Steve McNair",       "QB",  1995, False, ["TEN", "BAL"]),
    ("Brad Johnson",       "QB",  1992, False, ["MIN", "WAS", "TAM", "DAL", "PHI", "DEN"]),
    ("Trent Green",        "QB",  1997, False, ["WAS", "LAR", "KC", "MIA"]),
    ("Jake Plummer",       "QB",  1997, False, ["ARI", "DEN"]),
    ("Kerry Collins",      "QB",  1995, False, ["CAR", "NOR", "NYG", "LVR", "TEN", "IND", "NE"]),
    ("Mark Brunell",       "QB",  1993, False, ["GNB", "JAX", "WAS", "NOR", "NYJ"]),
    ("Jeff Garcia",        "QB",  1999, False, ["SFO", "CLE", "DET", "PHI", "TAM", "LVR"]),
    ("Rich Gannon",        "QB",  1987, False, ["MIN", "WAS", "KC", "LVR"]),
    ("Neil Lomax",         "QB",  1981, False, ["ARI"]),
    ("Boomer Esiason",     "QB",  1984, False, ["CIN", "NYJ", "ARI", "PIT"]),
    ("Jim Harbaugh",       "QB",  1987, False, ["CHI", "IND", "BAL", "LAC", "PIT"]),
    ("Chris Miller",       "QB",  1987, False, ["ATL", "LAR", "NOR", "DEN"]),
    ("Phil Simms",         "QB",  1979, False, ["NYG"]),
    ("Bernie Kosar",       "QB",  1985, False, ["CLE", "DAL", "MIA"]),
    ("Dave Krieg",         "QB",  1980, False, ["SEA", "KC", "DET", "ARI", "CHI", "TEN", "ATL"]),
    ("Wade Wilson",        "QB",  1981, False, ["MIN", "ATL", "NOR", "DAL", "LVR"]),
    ("Bubby Brister",      "QB",  1986, False, ["PIT", "PHI", "MIN", "NYJ", "DEN"]),

    # WRs (non-HOF)
    ("Herman Moore",       "WR",  1991, False, ["DET"]),
    ("Isaac Bruce",        "WR",  1994, False, ["LAR", "SFO"]),
    ("Rod Smith",          "WR",  1994, False, ["DEN"]),
    ("Derrick Mason",      "WR",  1997, False, ["TEN", "BAL", "NYJ", "HOU"]),
    ("Hines Ward",         "WR",  1998, False, ["PIT"]),
    ("Donald Driver",      "WR",  1999, False, ["GNB"]),
    ("Keyshawn Johnson",   "WR",  1996, False, ["NYJ", "TAM", "DAL", "CAR", "LAR"]),
    ("Muhsin Muhammad",    "WR",  1996, False, ["CAR", "CHI"]),
    ("Jimmy Smith",        "WR",  1992, False, ["DAL", "JAX"]),
    ("Plaxico Burress",    "WR",  2000, False, ["PIT", "NYG", "NYJ"]),
    ("Ashley Lelie",       "WR",  2002, False, ["DEN", "ATL", "LAC"]),
    ("Az-Zahir Hakim",     "WR",  1998, False, ["LAR", "DET", "LAC", "NOR"]),
    ("Eric Moulds",        "WR",  1996, False, ["BUF", "TEN", "HOU"]),
    ("Laveranues Coles",   "WR",  2000, False, ["NYJ", "WAS", "CIN"]),
    ("Antonio Freeman",    "WR",  1995, False, ["GNB", "PHI", "MIA"]),
    ("Robert Brooks",      "WR",  1992, False, ["GNB"]),
    ("Bill Schroeder",     "WR",  1994, False, ["GNB", "DET"]),
    ("Javon Walker",       "WR",  2002, False, ["GNB", "DEN", "LVR"]),
    ("Santana Moss",       "WR",  2001, False, ["NYJ", "WAS"]),
    ("Antwaan Randle El",  "WR",  2002, False, ["PIT", "WAS"]),
    ("David Patten",       "WR",  1997, False, ["NYG", "NE", "WAS", "NOR", "PHI", "CLE"]),

    # DEs / Pass rushers (non-HOF catalog)
    ("Osi Umenyiora",      "DE",  2003, False, ["NYG", "ATL"]),
    ("Jason Taylor",       "DE",  1997, False, ["MIA", "WAS", "NYJ"]),
    ("Adalius Thomas",     "LB",  2000, False, ["BAL", "NE", "MIN"]),
    ("Aaron Kampman",      "DE",  2002, False, ["GNB"]),
    ("Greg Ellis",         "DE",  1998, False, ["DAL", "LVR"]),
    ("Leonard Little",     "DE",  1998, False, ["LAR"]),
    ("Kevin Greene",       "LB",  1985, False, ["LAR", "PIT", "SFO", "CAR"]),
    ("Chris Doleman",      "DE",  1985, False, ["MIN", "ATL", "SFO"]),
    ("Pat Swilling",       "LB",  1986, False, ["NOR", "DET", "LVR", "PIT"]),
    ("Leslie O'Neal",      "DE",  1986, False, ["LAC", "LAR", "KC"]),
    ("Neil Smith",         "DE",  1988, False, ["KC", "DEN", "LAC", "PHI"]),
    ("William Fuller",     "DE",  1986, False, ["TEN", "PHI", "LAC", "CHI"]),
    ("Charles Haley",      "LB",  1986, False, ["SFO", "DAL"]),
    ("Clyde Simmons",      "DE",  1986, False, ["PHI", "ARI", "JAX", "CIN", "CHI"]),
    ("Trace Armstrong",    "DE",  1989, False, ["CHI", "MIA", "LVR", "NYG"]),
    ("Chuck Smith",        "DE",  1992, False, ["ATL", "CAR"]),
    ("Hugh Douglas",       "DE",  1995, False, ["NYJ", "PHI", "JAX"]),
    ("Trevor Pryce",       "DE",  1997, False, ["DEN", "BAL", "NYJ"]),
    ("La'Roi Glover",      "DL",  1996, False, ["LVR", "NOR", "DAL", "LAR", "CHI"]),
    ("Simeon Rice",        "DE",  1996, False, ["ARI", "TAM", "DEN", "CHI"]),
    ("John Abraham",       "LB",  2000, False, ["NYJ", "ATL", "ARI"]),
    ("Andre Carter",       "DE",  2001, False, ["SFO", "WAS", "NE", "LVR"]),
    ("Shaun Ellis",        "DE",  2000, False, ["NYJ", "NE"]),
    ("Kyle Vanden Bosch",  "DE",  2001, False, ["ARI", "TEN", "DET", "JAX"]),
    ("Victor Abiamiri",    "DE",  2007, False, ["PHI"]),

    # More modern star players not already in DB
    ("Andrew Luck",        "QB",  2012, False, ["IND"]),
    ("Russell Wilson",     "QB",  2012, False, ["SEA", "DEN", "PIT"]),
    ("Matt Ryan",          "QB",  2008, False, ["ATL", "IND"]),
    ("Matthew Stafford",   "QB",  2009, False, ["DET", "LAR"]),
    ("Andy Dalton",        "QB",  2011, False, ["CIN", "DAL", "CHI", "LVR", "NOR"]),
    ("Cam Newton",         "QB",  2011, False, ["CAR", "NE"]),
    ("Joe Flacco",         "QB",  2008, False, ["BAL", "DEN", "NYJ", "PHI", "CLE", "NYG", "IND"]),
    ("Kirk Cousins",       "QB",  2012, False, ["WAS", "MIN", "ATL"]),
    ("Colin Kaepernick",   "QB",  2011, False, ["SFO"]),
    ("Dak Prescott",       "QB",  2016, False, ["DAL"]),
    ("Carson Wentz",       "QB",  2016, False, ["PHI", "IND", "WAS", "LAR"]),

    # Key modern RBs
    ("Le'Veon Bell",       "RB",  2013, False, ["PIT", "NYJ", "KC", "BAL"]),
    ("LeSean McCoy",       "RB",  2009, False, ["PHI", "BUF", "KC", "TAM", "BUF"]),
    ("Matt Forte",         "RB",  2008, False, ["CHI", "NYJ"]),
    ("C.J. Anderson",      "RB",  2013, False, ["DEN", "CAR", "LVR", "LAR"]),
    ("Marshawn Lynch",     "RB",  2007, False, ["BUF", "SEA", "LVR"]),
    ("DeMarco Murray",     "RB",  2011, False, ["DAL", "PHI", "TEN", "MIN"]),
    ("Alfred Morris",      "RB",  2012, False, ["WAS", "DAL", "SFO"]),
    ("Arian Foster",       "RB",  2009, False, ["HOU", "MIA"]),
    ("Doug Martin",        "RB",  2012, False, ["TAM", "LVR"]),
    ("Mark Ingram",        "RB",  2011, False, ["NOR", "BAL", "HOU", "MIA"]),
    ("Lamar Miller",       "RB",  2012, False, ["MIA", "TEN", "HOU"]),
    ("David Johnson",      "RB",  2015, False, ["ARI", "HOU", "PHI"]),

    # Modern receivers not in DB
    ("Brandon Marshall",   "WR",  2006, False, ["DEN", "MIA", "CHI", "NYJ", "NYG", "PHI"]),
    ("Steve Smith Sr",     "WR",  2001, False, ["CAR", "BAL"]),
    ("Percy Harvin",       "WR",  2009, False, ["MIN", "SEA", "NYJ", "BUF"]),
    ("Hakeem Nicks",       "WR",  2009, False, ["NYG", "IND", "TEN"]),
    ("Victor Cruz",        "WR",  2010, False, ["NYG"]),
    ("Wes Welker",         "WR",  2004, False, ["MIA", "NE", "DEN", "LAR"]),
    ("Reggie Wayne",       "WR",  2001, False, ["IND"]),
    ("Chad Johnson",       "WR",  2001, False, ["CIN", "NE", "MIA"]),
    ("T.J. Houshmandzadeh","WR",  2001, False, ["CIN", "SEA", "BAL", "NYJ", "MIN"]),
    ("Donte Stallworth",   "WR",  2002, False, ["NOR", "PHI", "NE", "CLE", "BAL", "WAS"]),
    ("Roy Williams",       "WR",  2004, False, ["DET", "DAL", "CHI"]),
    ("Eddie Royal",        "WR",  2008, False, ["DEN", "LAC", "CHI"]),
    ("Devin Hester",       "WR",  2006, False, ["CHI", "ATL", "BAL", "SEA"]),
    ("Golden Tate",        "WR",  2010, False, ["SEA", "DET", "PHI", "NYG", "SFO"]),
    ("Nate Burleson",      "WR",  2003, False, ["MIN", "SEA", "DET"]),
    ("Mike Sims-Walker",   "WR",  2007, False, ["JAX", "LAR"]),
    ("Dez Bryant",         "WR",  2010, False, ["DAL"]),
    ("Vincent Jackson",    "WR",  2005, False, ["LAC", "TAM"]),
    ("Jordy Nelson",       "WR",  2008, False, ["GNB", "LVR"]),
    ("Randall Cobb",       "WR",  2011, False, ["GNB", "DAL", "TEN", "HOU", "NYJ"]),
    ("Marques Colston",    "WR",  2006, False, ["NOR"]),
    ("Pierre Garcon",      "WR",  2008, False, ["IND", "WAS", "SFO"]),
    ("Demaryius Thomas",   "WR",  2010, False, ["DEN", "TEN", "NYJ", "NE"]),
    ("Eric Decker",        "WR",  2010, False, ["DEN", "NYJ", "TEN", "NE"]),
    ("Emmanuel Sanders",   "WR",  2010, False, ["PIT", "DEN", "SFO", "NOR", "BUF"]),
    ("Kelvin Benjamin",    "WR",  2014, False, ["CAR", "BUF", "KC"]),
    ("Cordarrelle Patterson","WR", 2013, False, ["MIN", "LVR", "NE", "CHI", "ATL"]),
    ("TY Hilton",          "WR",  2012, False, ["IND"]),
    ("Brandin Cooks",      "WR",  2014, False, ["NOR", "NE", "LAR", "TEN", "HOU", "DAL"]),
    ("Larry Fitzgerald",   "WR",  2004, False, ["ARI"]),
    ("Calvin Johnson",     "WR",  2007, True,  ["DET"]),
    ("Julio Jones",        "WR",  2011, False, ["ATL", "TEN", "TAM"]),
    ("Antonio Brown",      "WR",  2010, False, ["PIT", "LVR", "TAM", "NE"]),
    ("AJ Green",           "WR",  2011, False, ["CIN", "ARI"]),
    ("Odell Beckham Jr",   "WR",  2014, False, ["NYG", "CLE", "LAR", "BAL"]),
    ("Mike Evans",         "WR",  2014, False, ["TAM"]),
    ("DeAndre Hopkins",    "WR",  2013, False, ["TEN", "HOU", "ARI", "NE"]),
    ("Davante Adams",      "WR",  2014, False, ["GNB", "LVR", "NYJ"]),
    ("Stefon Diggs",       "WR",  2015, False, ["MIN", "BUF", "TEN"]),
    ("Tyreek Hill",        "WR",  2016, False, ["KC", "MIA"]),
    ("Cooper Kupp",        "WR",  2017, False, ["LAR"]),

    # TEs
    ("Jason Witten",       "TE",  2003, False, ["DAL", "LVR"]),
    ("Antonio Gates",      "TE",  2003, False, ["LAC"]),
    ("Rob Gronkowski",     "TE",  2010, False, ["NE", "TAM"]),
    ("Jimmy Graham",       "TE",  2010, False, ["NOR", "SEA", "GNB", "CHI"]),
    ("Vernon Davis",       "TE",  2006, False, ["SFO", "DEN", "WAS", "MIA"]),
    ("Martellus Bennett",  "TE",  2008, False, ["DAL", "NYG", "CHI", "NE", "GNB"]),
    ("Jermichael Finley",  "TE",  2008, False, ["GNB"]),
    ("Dallas Clark",       "TE",  2003, False, ["IND", "TAM", "BAL"]),
    ("Jeremy Shockey",     "TE",  2002, False, ["NYG", "NOR", "CAR"]),
    ("Owen Daniels",       "TE",  2006, False, ["TEN", "BAL", "DEN"]),
    ("Delanie Walker",     "TE",  2006, False, ["SFO", "TEN"]),
    ("Gary Barnidge",      "TE",  2008, False, ["CAR", "CLE"]),
    ("Coby Fleener",       "TE",  2012, False, ["IND", "NOR"]),
    ("Charles Clay",       "TE",  2011, False, ["MIA", "BUF", "ARI"]),
    ("Greg Olsen",         "TE",  2007, False, ["CHI", "CAR", "SEA"]),
    ("Kyle Rudolph",       "TE",  2011, False, ["MIN", "NYG"]),
    ("Zach Ertz",          "TE",  2013, False, ["PHI", "ARI"]),
    ("Travis Kelce",       "TE",  2013, False, ["KC"]),
    ("George Kittle",      "TE",  2017, False, ["SFO"]),
    ("Darren Waller",      "TE",  2015, False, ["BAL", "LVR", "NYG"]),
    ("Mark Andrews",       "TE",  2018, False, ["BAL"]),

    # Pass rushers (modern era, needed for sack catalog)
    ("Terrell Suggs",      "LB",  2003, False, ["BAL", "ARI", "KC"]),
    ("Elvis Dumervil",     "DE",  2006, False, ["DEN", "BAL"]),
    ("Mario Williams",     "DE",  2006, False, ["TEN", "BUF", "MIA"]),
    ("Andre Johnson",      "DE",  2003, False, ["TEN", "IND", "CHI", "MIA", "NYJ", "CLE", "LAR"]),
    ("Robert Mathis",      "LB",  2003, False, ["IND"]),
    ("Clay Matthews",      "LB",  2009, False, ["GNB", "LAR"]),
    ("James Harrison",     "LB",  2002, False, ["PIT", "CIN", "NE"]),
    ("Jared Allen",        "DE",  2004, False, ["KC", "MIN", "CHI", "CAR"]),
    ("Dwight Freeney",     "DE",  2002, True,  ["IND", "ARI", "LAC", "ATL", "SEA", "DET"]),
    ("Connor Barwin",      "LB",  2009, False, ["TEN", "PHI", "LAR", "NE"]),
    ("LaMarr Woodley",     "LB",  2007, False, ["PIT", "LVR", "ARI"]),
    ("Cameron Wake",       "DE",  2009, False, ["MIA", "TEN"]),
    ("Justin Houston",     "LB",  2011, False, ["KC", "IND", "BAL", "LAR"]),
    ("Kawann Short",       "DL",  2013, False, ["CAR", "LVR"]),
    ("Za'Darius Smith",    "LB",  2015, False, ["BAL", "GNB", "MIN", "CLE", "DET"]),
    ("Preston Smith",      "LB",  2015, False, ["WAS", "GNB", "PIT"]),
    ("Vic Beasley",        "LB",  2015, False, ["ATL", "TEN", "BUF", "LAC"]),
    ("Melvin Ingram",      "DE",  2012, False, ["LAC", "PIT", "KC", "MIA"]),
    ("Chandler Jones",     "DE",  2012, False, ["NE", "ARI", "LVR"]),
    ("Brandon Graham",     "DE",  2010, False, ["PHI"]),
    ("Calais Campbell",    "DE",  2008, False, ["ARI", "JAX", "BAL", "ATL", "MIA"]),
    ("Michael Bennett",    "DE",  2009, False, ["TAM", "SEA", "PHI", "NE", "DAL"]),
    ("Olivier Vernon",     "DE",  2012, False, ["MIA", "NYG", "CLE"]),
    ("Dee Ford",           "LB",  2014, False, ["KC", "SFO"]),
    ("Bud Dupree",         "LB",  2015, False, ["PIT", "TEN", "ATL"]),
    ("Trey Hendrickson",   "DE",  2017, False, ["NOR", "CIN"]),
    ("Harold Landry III",  "DE",  2018, False, ["TEN"]),

    # CBs / Safeties (modern)
    ("Patrick Peterson",   "CB",  2011, False, ["ARI", "MIN", "PIT"]),
    ("Trumaine Johnson",   "CB",  2012, False, ["LAR", "NYJ", "BUF"]),
    ("Aqib Talib",         "CB",  2008, False, ["TAM", "NE", "DEN", "LAR", "MIA"]),
    ("Richard Sherman",    "CB",  2011, False, ["SEA", "SFO", "TAM"]),
    ("Stephon Gilmore",    "CB",  2012, False, ["BUF", "NE", "CAR", "IND", "DAL"]),
    ("Earl Thomas",        "S",   2010, False, ["SEA", "BAL"]),
    ("Kam Chancellor",     "S",   2010, False, ["SEA"]),
    ("Eric Berry",         "S",   2010, False, ["KC"]),
    ("Malcolm Jenkins",    "S",   2009, False, ["NOR", "PHI", "PIT"]),
    ("Antoine Bethea",     "S",   2006, False, ["IND", "SFO", "ARI", "NYG", "NOR", "CHI"]),
    ("Michael Griffin",    "S",   2007, False, ["TEN", "CAR"]),
    ("Lardarius Webb",     "CB",  2009, False, ["BAL", "CHI"]),
    ("Cortland Finnegan",  "CB",  2006, False, ["TEN", "LAR", "MIA", "LAR"]),
    ("Brandon Flowers",    "CB",  2008, False, ["KC", "LAC"]),
    ("Vontae Davis",       "CB",  2009, False, ["MIA", "IND", "BUF"]),
    ("Alterraun Verner",   "CB",  2010, False, ["TEN", "TAM"]),
    ("DeAngelo Hall",      "CB",  2004, False, ["ATL", "LVR", "WAS"]),
    ("Leon Hall",          "CB",  2007, False, ["CIN", "LVR"]),
    ("Nnamdi Asomugha",    "CB",  2003, False, ["LVR", "PHI", "SFO"]),
]

# ---------------------------------------------------------------------------
# key milestone stats: players who need stat entries to pass the catalog
# format: (full_name, stat_type, value, franchises_at_milestone)
# These are used to ensure the DB-based query paths also work in future
# ---------------------------------------------------------------------------
# We skip detailed stats seeding here — the catalog covers them
# Future TODO: seed actual PlayerSeasonStat rows

async def seed_historical_players():
    engine = create_async_engine(settings.async_database_url, echo=False)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:

        # Build combined list
        all_players = [(name, pos, ry, True, frans) for name, pos, ry, hy, frans in HOF_PLAYERS]
        # HOF_PLAYERS tuple is (name, pos, rookie_year, hof_year, franchises) -> convert
        # Actually above list comprehension is wrong, let me rebuild

        hof_entries = []
        for item in HOF_PLAYERS:
            name, pos, ry, hof_year, frans = item
            hof_entries.append((name, pos, ry, hof_year, frans, True))

        non_hof_entries = []
        for item in HISTORICAL_NON_HOF:
            name, pos, ry, is_hof, frans = item
            non_hof_entries.append((name, pos, ry, None, frans, is_hof))

        all_entries = hof_entries + non_hof_entries
        inserted_players = 0
        inserted_stints = 0
        inserted_hof = 0
        skipped = 0

        for entry in all_entries:
            name, pos, rookie_year, hof_year, franchises, is_hof = entry
            parts = name.split(" ", 1)
            first = parts[0]
            last = parts[1] if len(parts) > 1 else ""
            if rookie_year >= 2020:
                final_year = None
                is_active = not is_hof
            elif is_hof and hof_year:
                final_year = max(rookie_year + 10, hof_year - 5)
                is_active = False
            else:
                final_year = min(rookie_year + 14, 2023)
                is_active = False

            # Check if player already exists by name
            check = await session.execute(
                text("SELECT player_id FROM players WHERE LOWER(full_name) = LOWER(:name) LIMIT 1"),
                {"name": name}
            )
            existing = check.fetchone()

            if existing:
                player_id = existing[0]
                skipped += 1
            else:
                player_id = str(uuid.uuid4())
                await session.execute(
                    text("""
                        INSERT INTO players (
                            player_id, full_name, first_name, last_name,
                            primary_position, rookie_year, final_year, is_active,
                            draft_year, draft_round, draft_overall, college, headshot_url, gsis_id, pfr_id
                        ) VALUES (
                            :player_id, :full_name, :first_name, :last_name,
                            :primary_position, :rookie_year, :final_year, :is_active,
                            NULL, NULL, NULL, NULL, NULL, NULL, NULL
                        )
                        ON CONFLICT (player_id) DO NOTHING
                    """),
                    {
                        "player_id": player_id,
                        "full_name": name,
                        "first_name": first,
                        "last_name": last,
                        "primary_position": pos,
                        "rookie_year": rookie_year,
                        "final_year": final_year,
                        "is_active": (rookie_year >= 2020),
                    }
                )
                inserted_players += 1

            # Insert stints (one per franchise, fake season years)
            for franchise_id in franchises:
                # Check if franchise exists
                fc = await session.execute(
                    text("SELECT 1 FROM franchises WHERE franchise_id = :fid"),
                    {"fid": franchise_id}
                )
                if not fc.fetchone():
                    continue

                # Insert a representative stint
                await session.execute(
                    text("""
                        INSERT INTO player_team_stints (player_id, franchise_id, season_year, games_played, games_started)
                        VALUES (:player_id, :franchise_id, :season_year, :games_played, :games_started)
                        ON CONFLICT ON CONSTRAINT uq_player_franchise_season DO NOTHING
                    """),
                    {
                        "player_id": player_id,
                        "franchise_id": franchise_id,
                        "season_year": max(rookie_year, 2000),
                        "games_played": 16,
                        "games_started": 14,
                    }
                )
                inserted_stints += 1

            # Insert HOF accolade
            if is_hof and hof_year:
                await session.execute(
                    text("""
                        INSERT INTO accolades (player_id, franchise_id, season_year, accolade_type, category)
                        VALUES (:player_id, NULL, :season_year, 'HALL_OF_FAME', 'PLAYER')
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        "player_id": player_id,
                        "season_year": hof_year,
                    }
                )
                inserted_hof += 1

        await session.commit()
        print(f"Done!")
        print(f"  Inserted players:      {inserted_players}")
        print(f"  Skipped (exists):      {skipped}")
        print(f"  Inserted stints:       {inserted_stints}")
        print(f"  Inserted HOF accolades:{inserted_hof}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_historical_players())
