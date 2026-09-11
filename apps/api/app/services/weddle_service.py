from datetime import date
import random
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas.weddle import (
    AttributeComparison,
    WeddleComparisonAttributes,
    WeddleGuessComparison,
    WeddleGuessResponse,
    WeddlePlayer,
)

# ---------------------------------------------------------------------------
# Dynamic Age Helper
# ---------------------------------------------------------------------------
def compute_player_age(birth_date: Optional[date], reference_date: Optional[date] = None) -> Optional[int]:
    """
    Computes real-time age dynamically relative to reference_date (defaults to date.today()).
    Accurately accounts for leap years and exact month/day boundaries.
    """
    if not birth_date:
        return None
    ref = reference_date or date.today()
    return (
        ref.year
        - birth_date.year
        - ((ref.month, ref.day) < (birth_date.month, birth_date.day))
    )


# ---------------------------------------------------------------------------
# NFL Team Franchise Metadata (Conferences & Divisions)
# ---------------------------------------------------------------------------
TEAM_METADATA: Dict[str, Dict[str, str]] = {
    # AFC East
    "BUF": {"conference": "AFC", "division": "East", "city": "Buffalo", "name": "Bills"},
    "MIA": {"conference": "AFC", "division": "East", "city": "Miami", "name": "Dolphins"},
    "NWE": {"conference": "AFC", "division": "East", "city": "New England", "name": "Patriots"},
    "NE":  {"conference": "AFC", "division": "East", "city": "New England", "name": "Patriots"},
    "NYJ": {"conference": "AFC", "division": "East", "city": "New York", "name": "Jets"},
    # AFC North
    "BAL": {"conference": "AFC", "division": "North", "city": "Baltimore", "name": "Ravens"},
    "CIN": {"conference": "AFC", "division": "North", "city": "Cincinnati", "name": "Bengals"},
    "CLE": {"conference": "AFC", "division": "North", "city": "Cleveland", "name": "Browns"},
    "PIT": {"conference": "AFC", "division": "North", "city": "Pittsburgh", "name": "Steelers"},
    # AFC South
    "HOU": {"conference": "AFC", "division": "South", "city": "Houston", "name": "Texans"},
    "IND": {"conference": "AFC", "division": "South", "city": "Indianapolis", "name": "Colts"},
    "JAX": {"conference": "AFC", "division": "South", "city": "Jacksonville", "name": "Jaguars"},
    "JAC": {"conference": "AFC", "division": "South", "city": "Jacksonville", "name": "Jaguars"},
    "TEN": {"conference": "AFC", "division": "South", "city": "Tennessee", "name": "Titans"},
    # AFC West
    "DEN": {"conference": "AFC", "division": "West", "city": "Denver", "name": "Broncos"},
    "KC":  {"conference": "AFC", "division": "West", "city": "Kansas City", "name": "Chiefs"},
    "KAN": {"conference": "AFC", "division": "West", "city": "Kansas City", "name": "Chiefs"},
    "LAC": {"conference": "AFC", "division": "West", "city": "Los Angeles", "name": "Chargers"},
    "LVR": {"conference": "AFC", "division": "West", "city": "Las Vegas", "name": "Raiders"},
    "LV":  {"conference": "AFC", "division": "West", "city": "Las Vegas", "name": "Raiders"},
    # NFC East
    "DAL": {"conference": "NFC", "division": "East", "city": "Dallas", "name": "Cowboys"},
    "NYG": {"conference": "NFC", "division": "East", "city": "New York", "name": "Giants"},
    "PHI": {"conference": "NFC", "division": "East", "city": "Philadelphia", "name": "Eagles"},
    "WAS": {"conference": "NFC", "division": "East", "city": "Washington", "name": "Commanders"},
    "WSH": {"conference": "NFC", "division": "East", "city": "Washington", "name": "Commanders"},
    # NFC North
    "CHI": {"conference": "NFC", "division": "North", "city": "Chicago", "name": "Bears"},
    "DET": {"conference": "NFC", "division": "North", "city": "Detroit", "name": "Lions"},
    "GNB": {"conference": "NFC", "division": "North", "city": "Green Bay", "name": "Packers"},
    "GB":  {"conference": "NFC", "division": "North", "city": "Green Bay", "name": "Packers"},
    "MIN": {"conference": "NFC", "division": "North", "city": "Minnesota", "name": "Vikings"},
    # NFC South
    "ATL": {"conference": "NFC", "division": "South", "city": "Atlanta", "name": "Falcons"},
    "CAR": {"conference": "NFC", "division": "South", "city": "Carolina", "name": "Panthers"},
    "NOR": {"conference": "NFC", "division": "South", "city": "New Orleans", "name": "Saints"},
    "NO":  {"conference": "NFC", "division": "South", "city": "New Orleans", "name": "Saints"},
    "TAM": {"conference": "NFC", "division": "South", "city": "Tampa Bay", "name": "Buccaneers"},
    "TB":  {"conference": "NFC", "division": "South", "city": "Tampa Bay", "name": "Buccaneers"},
    # NFC West
    "ARI": {"conference": "NFC", "division": "West", "city": "Arizona", "name": "Cardinals"},
    "LAR": {"conference": "NFC", "division": "West", "city": "Los Angeles", "name": "Rams"},
    "LA":  {"conference": "NFC", "division": "West", "city": "Los Angeles", "name": "Rams"},
    "SFO": {"conference": "NFC", "division": "West", "city": "San Francisco", "name": "49ers"},
    "SF":  {"conference": "NFC", "division": "West", "city": "San Francisco", "name": "49ers"},
    "SEA": {"conference": "NFC", "division": "West", "city": "Seattle", "name": "Seahawks"},
}

# ---------------------------------------------------------------------------
# Positional Subgroups for Partial/Yellow Match Grading
# ---------------------------------------------------------------------------
POSITION_SUBGROUPS: List[Set[str]] = [
    {"OT", "T", "OG", "G", "C", "OL", "LT", "RT", "LG", "RG"},  # Offensive Line
    {"CB", "S", "FS", "SS", "DB"},                              # Defensive Back
    {"DE", "DT", "NT", "DL", "EDGE"},                           # Defensive Line / Edge
    {"LB", "ILB", "OLB", "MLB"},                                # Linebackers
    {"WR", "TE"},                                                # Pass Catchers / Receivers
    {"RB", "FB"},                                                # Running Backs
    {"QB"},                                                      # Quarterbacks
    {"K", "P", "LS"},                                            # Specialists
]

OFFENSIVE_POSITIONS: Set[str] = {
    "QB", "RB", "FB", "WR", "TE", "OT", "T", "OG", "G", "C", "OL", "LT", "RT", "LG", "RG"
}

DEFENSIVE_POSITIONS: Set[str] = {
    "DE", "DT", "NT", "DL", "EDGE", "OLB", "ILB", "MLB", "LB", "CB", "S", "FS", "SS", "DB"
}


def format_height(inches: int) -> str:
    """Formats height in inches into standard feet'inches\" notation."""
    feet = inches // 12
    rem = inches % 12
    return f"{feet}'{rem}\""


# ---------------------------------------------------------------------------
# Rich Verified Active NFL Player Directory with Canonical Birth Dates
# All ages dynamically computed relative to CURRENT_DATE / evaluation date.
# ---------------------------------------------------------------------------
ACTIVE_NFL_PLAYERS: List[Dict[str, Any]] = [
    # Quarterbacks
    {"player_id": "00-0035710", "full_name": "Daniel Jones", "team": "IND", "position": "QB", "birth_date": "1997-05-27", "height_inches": 77, "jersey_number": 17, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3917792.png&w=350&h=254"},
    {"player_id": "00-0039851", "full_name": "Drake Maye", "team": "NE", "position": "QB", "birth_date": "2002-08-30", "height_inches": 76, "jersey_number": 10, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4431452.png&w=350&h=254"},
    {"player_id": "00-0033873", "full_name": "Patrick Mahomes", "team": "KC", "position": "QB", "birth_date": "1995-09-17", "height_inches": 74, "jersey_number": 15, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3139477.png&w=350&h=254"},
    {"player_id": "00-0034796", "full_name": "Lamar Jackson", "team": "BAL", "position": "QB", "birth_date": "1997-01-07", "height_inches": 74, "jersey_number": 8, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3916387.png&w=350&h=254"},
    {"player_id": "00-0034857", "full_name": "Josh Allen", "team": "BUF", "position": "QB", "birth_date": "1996-05-21", "height_inches": 77, "jersey_number": 17, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3918298.png&w=350&h=254"},
    {"player_id": "00-0036442", "full_name": "Joe Burrow", "team": "CIN", "position": "QB", "birth_date": "1996-12-10", "height_inches": 76, "jersey_number": 9, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3915511.png&w=350&h=254"},
    {"player_id": "00-0036212", "full_name": "Jalen Hurts", "team": "PHI", "position": "QB", "birth_date": "1998-08-07", "height_inches": 73, "jersey_number": 1, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4040715.png&w=350&h=254"},
    {"player_id": "00-0039163", "full_name": "C.J. Stroud", "team": "HOU", "position": "QB", "birth_date": "2001-10-03", "height_inches": 75, "jersey_number": 7, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4432577.png&w=350&h=254"},
    {"player_id": "00-0036355", "full_name": "Justin Herbert", "team": "LAC", "position": "QB", "birth_date": "1998-03-10", "height_inches": 78, "jersey_number": 10, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4038941.png&w=350&h=254"},
    {"player_id": "00-0036971", "full_name": "Trevor Lawrence", "team": "JAX", "position": "QB", "birth_date": "1999-10-06", "height_inches": 78, "jersey_number": 16, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/36971.png&w=350&h=254"},
    {"player_id": "00-0037834", "full_name": "Brock Purdy", "team": "SF", "position": "QB", "birth_date": "1999-12-27", "height_inches": 73, "jersey_number": 13, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4361741.png&w=350&h=254"},
    {"player_id": "00-0036264", "full_name": "Jordan Love", "team": "GB", "position": "QB", "birth_date": "1998-11-02", "height_inches": 76, "jersey_number": 10, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4036378.png&w=350&h=254"},
    {"player_id": "00-0033077", "full_name": "Dak Prescott", "team": "DAL", "position": "QB", "birth_date": "1993-07-29", "height_inches": 74, "jersey_number": 4, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/2577417.png&w=350&h=254"},
    {"player_id": "00-0033106", "full_name": "Jared Goff", "team": "DET", "position": "QB", "birth_date": "1994-10-14", "height_inches": 76, "jersey_number": 16, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3046779.png&w=350&h=254"},
    {"player_id": "00-0036226", "full_name": "Tua Tagovailoa", "team": "MIA", "position": "QB", "birth_date": "1998-03-02", "height_inches": 73, "jersey_number": 1, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4241479.png&w=350&h=254"},
    {"player_id": "00-0034844", "full_name": "Baker Mayfield", "team": "TB", "position": "QB", "birth_date": "1995-04-14", "height_inches": 73, "jersey_number": 6, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3052587.png&w=350&h=254"},
    {"player_id": "00-0035228", "full_name": "Kyler Murray", "team": "ARI", "position": "QB", "birth_date": "1997-08-07", "height_inches": 70, "jersey_number": 1, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3917315.png&w=350&h=254"},
    {"player_id": "00-0023459", "full_name": "Aaron Rodgers", "team": "NYJ", "position": "QB", "birth_date": "1983-12-02", "height_inches": 74, "jersey_number": 8, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/8439.png&w=350&h=254"},
    {"player_id": "00-0029604", "full_name": "Kirk Cousins", "team": "ATL", "position": "QB", "birth_date": "1988-08-19", "height_inches": 75, "jersey_number": 18, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/14880.png&w=350&h=254"},
    {"player_id": "draft2024-williams-cal01", "full_name": "Caleb Williams", "team": "CHI", "position": "QB", "birth_date": "2001-11-18", "height_inches": 73, "jersey_number": 18, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4431611.png&w=350&h=254"},
    {"player_id": "draft2024-daniels-jay01", "full_name": "Jayden Daniels", "team": "WAS", "position": "QB", "birth_date": "2000-12-18", "height_inches": 76, "jersey_number": 5, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4426348.png&w=350&h=254"},

    # Running Backs
    {"player_id": "00-0033280", "full_name": "Christian McCaffrey", "team": "SF", "position": "RB", "birth_date": "1996-06-07", "height_inches": 71, "jersey_number": 23, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3117251.png&w=350&h=254"},
    {"player_id": "00-0032764", "full_name": "Derrick Henry", "team": "BAL", "position": "RB", "birth_date": "1994-01-04", "height_inches": 75, "jersey_number": 22, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3043078.png&w=350&h=254"},
    {"player_id": "00-0034844-rb", "full_name": "Saquon Barkley", "team": "PHI", "position": "RB", "birth_date": "1997-02-09", "height_inches": 72, "jersey_number": 26, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3929630.png&w=350&h=254"},
    {"player_id": "00-0038596", "full_name": "Bijan Robinson", "team": "ATL", "position": "RB", "birth_date": "2002-01-30", "height_inches": 71, "jersey_number": 7, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4430737.png&w=350&h=254"},
    {"player_id": "00-0038597", "full_name": "Jahmyr Gibbs", "team": "DET", "position": "RB", "birth_date": "2002-03-20", "height_inches": 69, "jersey_number": 26, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4430740.png&w=350&h=254"},
    {"player_id": "00-0037835-rb", "full_name": "Breece Hall", "team": "NYJ", "position": "RB", "birth_date": "2001-05-31", "height_inches": 73, "jersey_number": 20, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4427366.png&w=350&h=254"},
    {"player_id": "00-0035700", "full_name": "Josh Jacobs", "team": "GB", "position": "RB", "birth_date": "1998-02-11", "height_inches": 70, "jersey_number": 8, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4047365.png&w=350&h=254"},
    {"player_id": "00-0036223", "full_name": "Jonathan Taylor", "team": "IND", "position": "RB", "birth_date": "1999-01-19", "height_inches": 70, "jersey_number": 28, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4242335.png&w=350&h=254"},
    {"player_id": "00-0033906", "full_name": "Alvin Kamara", "team": "NO", "position": "RB", "birth_date": "1995-07-25", "height_inches": 70, "jersey_number": 41, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3054850.png&w=350&h=254"},
    {"player_id": "00-0033293", "full_name": "Aaron Jones", "team": "MIN", "position": "RB", "birth_date": "1994-12-02", "height_inches": 69, "jersey_number": 33, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3042519.png&w=350&h=254"},
    {"player_id": "00-0034791", "full_name": "Nick Chubb", "team": "CLE", "position": "RB", "birth_date": "1995-12-27", "height_inches": 71, "jersey_number": 24, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3128720.png&w=350&h=254"},
    {"player_id": "00-0036980", "full_name": "Travis Etienne Jr.", "team": "JAX", "position": "RB", "birth_date": "1999-01-26", "height_inches": 70, "jersey_number": 1, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4239996.png&w=350&h=254"},
    {"player_id": "00-0037840", "full_name": "Kyren Williams", "team": "LAR", "position": "RB", "birth_date": "2000-08-26", "height_inches": 69, "jersey_number": 23, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4430704.png&w=350&h=254"},
    {"player_id": "00-0038590", "full_name": "De'Von Achane", "team": "MIA", "position": "RB", "birth_date": "2001-10-13", "height_inches": 69, "jersey_number": 28, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4429018.png&w=350&h=254"},

    # Wide Receivers
    {"player_id": "00-0038543", "full_name": "Jaxon Smith-Njigba", "team": "SEA", "position": "WR", "birth_date": "2002-02-14", "height_inches": 72, "jersey_number": 11, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4430878.png&w=350&h=254"},
    {"player_id": "00-0036322", "full_name": "Justin Jefferson", "team": "MIN", "position": "WR", "birth_date": "1999-06-16", "height_inches": 73, "jersey_number": 18, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4262921.png&w=350&h=254"},
    {"player_id": "00-0036900", "full_name": "Ja'Marr Chase", "team": "CIN", "position": "WR", "birth_date": "2000-03-01", "height_inches": 72, "jersey_number": 1, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4362628.png&w=350&h=254"},
    {"player_id": "00-0036358", "full_name": "CeeDee Lamb", "team": "DAL", "position": "WR", "birth_date": "1999-04-08", "height_inches": 74, "jersey_number": 88, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4241389.png&w=350&h=254"},
    {"player_id": "00-0033040", "full_name": "Tyreek Hill", "team": "MIA", "position": "WR", "birth_date": "1994-03-01", "height_inches": 70, "jersey_number": 10, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3116406.png&w=350&h=254"},
    {"player_id": "00-0036912", "full_name": "Amon-Ra St. Brown", "team": "DET", "position": "WR", "birth_date": "1999-10-24", "height_inches": 72, "jersey_number": 14, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4374302.png&w=350&h=254"},
    {"player_id": "00-0035676", "full_name": "A.J. Brown", "team": "NE", "position": "WR", "birth_date": "1997-06-30", "height_inches": 73, "jersey_number": 1, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4047646.png&w=350&h=254"},
    {"player_id": "00-0031388", "full_name": "Davante Adams", "team": "LV", "position": "WR", "birth_date": "1992-12-24", "height_inches": 73, "jersey_number": 17, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/16800.png&w=350&h=254"},
    {"player_id": "00-0031237", "full_name": "Mike Evans", "team": "TB", "position": "WR", "birth_date": "1993-08-21", "height_inches": 77, "jersey_number": 13, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/16737.png&w=350&h=254"},
    {"player_id": "00-0035640", "full_name": "DK Metcalf", "team": "SEA", "position": "WR", "birth_date": "1997-12-14", "height_inches": 76, "jersey_number": 14, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4047650.png&w=350&h=254"},
    {"player_id": "00-0037836", "full_name": "Garrett Wilson", "team": "NYJ", "position": "WR", "birth_date": "2000-07-22", "height_inches": 72, "jersey_number": 5, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4426515.png&w=350&h=254"},
    {"player_id": "00-0035685", "full_name": "Terry McLaurin", "team": "WAS", "position": "WR", "birth_date": "1995-09-15", "height_inches": 72, "jersey_number": 17, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3121422.png&w=350&h=254"},
    {"player_id": "00-0035677", "full_name": "Deebo Samuel", "team": "SF", "position": "WR", "birth_date": "1996-01-15", "height_inches": 72, "jersey_number": 1, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3126486.png&w=350&h=254"},
    {"player_id": "00-0036324", "full_name": "Brandon Aiyuk", "team": "SF", "position": "WR", "birth_date": "1998-03-17", "height_inches": 72, "jersey_number": 11, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4360438.png&w=350&h=254"},
    {"player_id": "00-0033908", "full_name": "Cooper Kupp", "team": "SEA", "position": "WR", "birth_date": "1993-06-15", "height_inches": 74, "jersey_number": 10, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/2977187.png&w=350&h=254"},
    {"player_id": "00-0034784", "full_name": "DJ Moore", "team": "CHI", "position": "WR", "birth_date": "1997-04-14", "height_inches": 72, "jersey_number": 2, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3915416.png&w=350&h=254"},
    {"player_id": "00-0037837", "full_name": "Chris Olave", "team": "NO", "position": "WR", "birth_date": "2000-06-27", "height_inches": 72, "jersey_number": 12, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4361370.png&w=350&h=254"},
    {"player_id": "00-0036913", "full_name": "DeVonta Smith", "team": "PHI", "position": "WR", "birth_date": "1998-11-14", "height_inches": 72, "jersey_number": 6, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4241478.png&w=350&h=254"},
    {"player_id": "draft2024-harrison-mar01", "full_name": "Marvin Harrison Jr.", "team": "ARI", "position": "WR", "birth_date": "2002-08-11", "height_inches": 75, "jersey_number": 18, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4432708.png&w=350&h=254"},
    {"player_id": "draft2024-nabers-mal01", "full_name": "Malik Nabers", "team": "NYG", "position": "WR", "birth_date": "2003-07-28", "height_inches": 72, "jersey_number": 1, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4430875.png&w=350&h=254"},

    # Tight Ends
    {"player_id": "00-0030506", "full_name": "Travis Kelce", "team": "KC", "position": "TE", "birth_date": "1989-10-05", "height_inches": 77, "jersey_number": 87, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/15847.png&w=350&h=254"},
    {"player_id": "00-0033859", "full_name": "George Kittle", "team": "SF", "position": "TE", "birth_date": "1993-10-09", "height_inches": 76, "jersey_number": 85, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/2976316.png&w=350&h=254"},
    {"player_id": "00-0034789", "full_name": "Mark Andrews", "team": "BAL", "position": "TE", "birth_date": "1995-09-06", "height_inches": 77, "jersey_number": 89, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3116365.png&w=350&h=254"},
    {"player_id": "00-0038598", "full_name": "Sam LaPorta", "team": "DET", "position": "TE", "birth_date": "2001-01-12", "height_inches": 76, "jersey_number": 87, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4430027.png&w=350&h=254"},
    {"player_id": "00-0037841", "full_name": "Trey McBride", "team": "ARI", "position": "TE", "birth_date": "1999-11-22", "height_inches": 76, "jersey_number": 85, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4361311.png&w=350&h=254"},
    {"player_id": "00-0035687", "full_name": "T.J. Hockenson", "team": "MIN", "position": "TE", "birth_date": "1997-07-03", "height_inches": 77, "jersey_number": 87, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4035687.png&w=350&h=254"},
    {"player_id": "00-0036914", "full_name": "Kyle Pitts", "team": "ATL", "position": "TE", "birth_date": "2000-10-06", "height_inches": 78, "jersey_number": 8, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4360248.png&w=350&h=254"},
    {"player_id": "draft2024-bowers-bro01", "full_name": "Brock Bowers", "team": "LV", "position": "TE", "birth_date": "2002-12-13", "height_inches": 76, "jersey_number": 89, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4432665.png&w=350&h=254"},

    # Offensive Line
    {"player_id": "00-0035220", "full_name": "Penei Sewell", "team": "DET", "position": "OT", "birth_date": "2000-10-09", "height_inches": 77, "jersey_number": 58, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4360799.png&w=350&h=254"},
    {"player_id": "00-0036327", "full_name": "Tristan Wirfs", "team": "TB", "position": "OT", "birth_date": "1999-01-24", "height_inches": 77, "jersey_number": 78, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4242337.png&w=350&h=254"},
    {"player_id": "00-0034848", "full_name": "Quenton Nelson", "team": "IND", "position": "OG", "birth_date": "1996-03-19", "height_inches": 77, "jersey_number": 56, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3122131.png&w=350&h=254"},
    {"player_id": "00-0036916", "full_name": "Creed Humphrey", "team": "KC", "position": "C", "birth_date": "1999-06-28", "height_inches": 76, "jersey_number": 52, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4241388.png&w=350&h=254"},
    {"player_id": "00-0036917", "full_name": "Rashawn Slater", "team": "LAC", "position": "OT", "birth_date": "1999-03-26", "height_inches": 76, "jersey_number": 70, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4240751.png&w=350&h=254"},

    # Edge / Defensive Line
    {"player_id": "00-0033887", "full_name": "Myles Garrett", "team": "LAR", "position": "DE", "birth_date": "1995-12-29", "height_inches": 76, "jersey_number": 95, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3122132.png&w=350&h=254"},
    {"player_id": "00-0033882", "full_name": "T.J. Watt", "team": "PIT", "position": "LB", "birth_date": "1994-10-11", "height_inches": 76, "jersey_number": 90, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3045282.png&w=350&h=254"},
    {"player_id": "00-0035236", "full_name": "Nick Bosa", "team": "SF", "position": "DE", "birth_date": "1997-10-23", "height_inches": 76, "jersey_number": 97, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4040605.png&w=350&h=254"},
    {"player_id": "00-0036964", "full_name": "Micah Parsons", "team": "DAL", "position": "LB", "birth_date": "1999-05-26", "height_inches": 75, "jersey_number": 11, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4361423.png&w=350&h=254"},
    {"player_id": "00-0035643", "full_name": "Maxx Crosby", "team": "LV", "position": "DE", "birth_date": "1997-08-22", "height_inches": 77, "jersey_number": 98, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3917794.png&w=350&h=254"},
    {"player_id": "00-0033108", "full_name": "Chris Jones", "team": "KC", "position": "DT", "birth_date": "1994-07-03", "height_inches": 78, "jersey_number": 95, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3045281.png&w=350&h=254"},
    {"player_id": "00-0037839", "full_name": "Aidan Hutchinson", "team": "DET", "position": "DE", "birth_date": "2000-08-09", "height_inches": 79, "jersey_number": 97, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4362629.png&w=350&h=254"},
    {"player_id": "00-0038599", "full_name": "Will Anderson Jr.", "team": "HOU", "position": "DE", "birth_date": "2001-09-02", "height_inches": 76, "jersey_number": 51, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4429022.png&w=350&h=254"},
    {"player_id": "00-0035235", "full_name": "Quinnen Williams", "team": "NYJ", "position": "DT", "birth_date": "1997-12-04", "height_inches": 75, "jersey_number": 95, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4040982.png&w=350&h=254"},
    {"player_id": "00-0035238", "full_name": "Brian Burns", "team": "NYG", "position": "DE", "birth_date": "1998-04-23", "height_inches": 77, "jersey_number": 0, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4035688.png&w=350&h=254"},
    {"player_id": "00-0032130", "full_name": "Danielle Hunter", "team": "HOU", "position": "DE", "birth_date": "1994-10-29", "height_inches": 77, "jersey_number": 55, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/2976560.png&w=350&h=254"},
    {"player_id": "00-0035645", "full_name": "Montez Sweat", "team": "CHI", "position": "DE", "birth_date": "1996-09-04", "height_inches": 78, "jersey_number": 98, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3139379.png&w=350&h=254"},
    {"player_id": "00-0033888", "full_name": "Trey Hendrickson", "team": "CIN", "position": "DE", "birth_date": "1994-12-05", "height_inches": 76, "jersey_number": 91, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3040149.png&w=350&h=254"},
    {"player_id": "00-0034788", "full_name": "Dexter Lawrence", "team": "NYG", "position": "DT", "birth_date": "1997-11-12", "height_inches": 76, "jersey_number": 97, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4040983.png&w=350&h=254"},

    # Linebackers
    {"player_id": "00-0034785", "full_name": "Roquan Smith", "team": "BAL", "position": "LB", "birth_date": "1997-04-08", "height_inches": 73, "jersey_number": 0, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3915189.png&w=350&h=254"},
    {"player_id": "00-0034786", "full_name": "Fred Warner", "team": "SF", "position": "LB", "birth_date": "1996-11-19", "height_inches": 75, "jersey_number": 54, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3124005.png&w=350&h=254"},
    {"player_id": "00-0029645", "full_name": "Demario Davis", "team": "NO", "position": "LB", "birth_date": "1989-01-11", "height_inches": 74, "jersey_number": 56, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/14979.png&w=350&h=254"},
    {"player_id": "00-0035646", "full_name": "Bobby Okereke", "team": "NYG", "position": "LB", "birth_date": "1996-07-29", "height_inches": 73, "jersey_number": 58, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3122134.png&w=350&h=254"},

    # Defensive Backs (Cornerbacks & Safeties)
    {"player_id": "00-0037835", "full_name": "Sauce Gardner", "team": "NYJ", "position": "CB", "birth_date": "2000-08-31", "height_inches": 75, "jersey_number": 1, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4428800.png&w=350&h=254"},
    {"player_id": "00-0036918", "full_name": "Patrick Surtain II", "team": "DEN", "position": "CB", "birth_date": "2000-04-14", "height_inches": 74, "jersey_number": 2, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4360249.png&w=350&h=254"},
    {"player_id": "00-0033110", "full_name": "Jalen Ramsey", "team": "MIA", "position": "CB", "birth_date": "1994-10-24", "height_inches": 73, "jersey_number": 5, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3045373.png&w=350&h=254"},
    {"player_id": "00-0037842", "full_name": "Trent McDuffie", "team": "KC", "position": "CB", "birth_date": "2000-09-13", "height_inches": 71, "jersey_number": 22, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4427020.png&w=350&h=254"},
    {"player_id": "00-0036328", "full_name": "Jaylon Johnson", "team": "CHI", "position": "CB", "birth_date": "1999-04-19", "height_inches": 72, "jersey_number": 1, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4241032.png&w=350&h=254"},
    {"player_id": "00-0037843", "full_name": "DaRon Bland", "team": "DAL", "position": "CB", "birth_date": "1999-07-12", "height_inches": 72, "jersey_number": 26, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4429813.png&w=350&h=254"},
    {"player_id": "00-0034787", "full_name": "Minkah Fitzpatrick", "team": "PIT", "position": "S", "birth_date": "1996-11-17", "height_inches": 73, "jersey_number": 39, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3915512.png&w=350&h=254"},
    {"player_id": "00-0037844", "full_name": "Kyle Hamilton", "team": "BAL", "position": "S", "birth_date": "2001-03-16", "height_inches": 76, "jersey_number": 14, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4429012.png&w=350&h=254"},
    {"player_id": "00-0034790", "full_name": "Jessie Bates III", "team": "ATL", "position": "S", "birth_date": "1997-02-26", "height_inches": 73, "jersey_number": 3, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3915415.png&w=350&h=254"},
    {"player_id": "00-0036329", "full_name": "Antoine Winfield Jr.", "team": "TB", "position": "S", "birth_date": "1998-08-16", "height_inches": 69, "jersey_number": 31, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4035689.png&w=350&h=254"},
    {"player_id": "00-0034792", "full_name": "Derwin James Jr.", "team": "LAC", "position": "S", "birth_date": "1996-08-03", "height_inches": 74, "jersey_number": 3, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3915513.png&w=350&h=254"},
]


class WeddleService:
    """
    Core domain service for the daily 'Guess the Player' (Weddle) mode.
    Handles deterministic target selection, player profile resolution,
    and 8-dimensional attribute comparison with directional indicators.
    """

    _catalog: Dict[str, WeddlePlayer] = {}
    _target_pool: List[WeddlePlayer] = []

    @classmethod
    def _initialize_catalog(cls) -> None:
        if cls._catalog:
            return

        for raw in ACTIVE_NFL_PLAYERS:
            team_meta = TEAM_METADATA.get(raw["team"].upper(), {"conference": "AFC", "division": "East"})
            pos = raw["position"].upper()
            side = "Offense" if pos in OFFENSIVE_POSITIONS else "Defense"
            h_inches = raw["height_inches"]

            b_date: Optional[date] = None
            if "birth_date" in raw and raw["birth_date"]:
                if isinstance(raw["birth_date"], str):
                    b_date = date.fromisoformat(raw["birth_date"])
                elif isinstance(raw["birth_date"], date):
                    b_date = raw["birth_date"]

            # Real-time dynamic age calculation
            computed_age = compute_player_age(b_date) if b_date else raw.get("age", 26)

            player = WeddlePlayer(
                player_id=raw["player_id"],
                full_name=raw["full_name"],
                headshot_url=raw.get("headshot_url"),
                team=raw["team"].upper(),
                side_of_ball=side,
                position=pos,
                conference=team_meta["conference"],
                division=team_meta["division"],
                birth_date=b_date,
                age=computed_age,
                height_inches=h_inches,
                height_formatted=format_height(h_inches),
                jersey_number=raw["jersey_number"],
            )
            cls._catalog[player.player_id] = player
            cls._catalog[player.full_name.lower().strip()] = player
            cls._target_pool.append(player)

    @classmethod
    def get_player(cls, identifier: str) -> Optional[WeddlePlayer]:
        """Looks up a player by ID or normalized full name."""
        cls._initialize_catalog()
        if not identifier:
            return None
        clean_id = identifier.strip()
        clean_name = clean_id.lower()
        return cls._catalog.get(clean_id) or cls._catalog.get(clean_name)

    @classmethod
    async def resolve_from_db(cls, db_player: Any, session: Any) -> WeddlePlayer:
        """
        Dynamically constructs or resolves a full WeddlePlayer model from a PostgreSQL Player entity.
        Queries player's most recent team stint to accurately reflect current/last franchise.
        """
        cls._initialize_catalog()

        # 1. Check if player is already in curated catalog by name or gsis_id
        matched = cls.get_player(db_player.full_name) or (
            cls.get_player(db_player.gsis_id) if getattr(db_player, "gsis_id", None) else None
        )
        if matched:
            # Recompute age dynamically if birth_date is available on DB player or matched player
            b_date = getattr(db_player, "birth_date", None) or matched.birth_date
            dyn_age = compute_player_age(b_date) if b_date else matched.age

            cloned = WeddlePlayer(
                player_id=db_player.player_id,
                full_name=matched.full_name,
                headshot_url=matched.headshot_url or getattr(db_player, "headshot_url", None),
                team=matched.team,
                side_of_ball=matched.side_of_ball,
                position=matched.position,
                conference=matched.conference,
                division=matched.division,
                birth_date=b_date,
                age=dyn_age,
                height_inches=matched.height_inches,
                height_formatted=matched.height_formatted,
                jersey_number=matched.jersey_number,
            )
            cls._catalog[db_player.player_id] = cloned
            return cloned

        # 2. Query most recent franchise stint from DB
        from app.db.models.player import PlayerTeamStint
        from sqlalchemy import select

        stmt_stint = select(PlayerTeamStint).where(
            PlayerTeamStint.player_id == db_player.player_id
        ).order_by(PlayerTeamStint.season_year.desc())
        stint = (await session.execute(stmt_stint)).scalars().first()
        team_code = stint.franchise_id.upper() if stint else "KC"

        # Position normalization
        raw_pos = (getattr(db_player, "primary_position", None) or "QB").upper()
        if raw_pos == "T":
            pos = "OT"
        elif raw_pos == "G":
            pos = "OG"
        elif raw_pos in {"FS", "SS"}:
            pos = "S"
        elif raw_pos in {"ILB", "MLB"}:
            pos = "LB"
        elif raw_pos in {"NT"}:
            pos = "DT"
        else:
            pos = raw_pos

        side = "Offense" if pos in OFFENSIVE_POSITIONS else "Defense"
        team_meta = TEAM_METADATA.get(team_code, {"conference": "AFC", "division": "East"})

        # Dynamic age resolution: prefer exact birth_date, fallback to career span
        db_birth_date = getattr(db_player, "birth_date", None)
        if db_birth_date:
            age = compute_player_age(db_birth_date)
        else:
            current_year = date.today().year
            rookie_year = getattr(db_player, "rookie_year", None)
            draft_year = getattr(db_player, "draft_year", None)
            if rookie_year and rookie_year > 1950:
                age = min(44, max(21, current_year - rookie_year + 22))
            elif draft_year and draft_year > 1950:
                age = min(44, max(21, current_year - draft_year + 22))
            else:
                age = 26

        # Sensible positional heights
        pos_heights = {
            "QB": 74, "WR": 73, "RB": 70, "FB": 71, "TE": 76,
            "OT": 77, "OG": 75, "C": 75, "OL": 76,
            "DE": 76, "DT": 75, "DL": 76, "EDGE": 76, "LB": 73,
            "CB": 72, "S": 73, "DB": 72, "K": 72, "P": 73, "LS": 74,
        }
        h_inches = pos_heights.get(pos, 73)

        # Deterministic jersey number from hash or jersey_number attribute
        db_jersey = getattr(db_player, "jersey_number", None)
        if db_jersey is not None and 0 <= db_jersey <= 99:
            h_num = db_jersey
        else:
            import hashlib
            h_num = (int(hashlib.md5(db_player.full_name.encode()).hexdigest(), 16) % 89) + 10

        player = WeddlePlayer(
            player_id=db_player.player_id,
            full_name=db_player.full_name,
            headshot_url=getattr(db_player, "headshot_url", None),
            team=team_code,
            side_of_ball=side,
            position=pos,
            conference=team_meta["conference"],
            division=team_meta["division"],
            birth_date=db_birth_date,
            age=age,
            height_inches=h_inches,
            height_formatted=format_height(h_inches),
            jersey_number=h_num,
        )

        cls._catalog[db_player.player_id] = player
        cls._catalog[db_player.full_name.lower().strip()] = player
        return player

    @classmethod
    def get_all_target_eligible_players(cls) -> List[WeddlePlayer]:
        """Returns the list of all invariant-valid active players for daily mystery selection."""
        cls._initialize_catalog()
        return list(cls._target_pool)

    @classmethod
    def select_daily_target(cls, target_date: date) -> WeddlePlayer:
        """
        Deterministically selects the mystery target player for a given calendar date.
        Formula: seed = int(target_date.strftime("%Y%m%d")) + 5503
        """
        cls._initialize_catalog()
        seed_value = int(target_date.strftime("%Y%m%d")) + 5503
        rng = random.Random(seed_value)
        pool = cls._target_pool
        chosen_index = rng.randint(0, len(pool) - 1)
        base_target = pool[chosen_index]

        # Re-evaluate target player's age dynamically relative to the target_date
        if base_target.birth_date:
            dyn_age = compute_player_age(base_target.birth_date, reference_date=target_date)
            if dyn_age != base_target.age:
                return base_target.model_copy(update={"age": dyn_age})
        return base_target

    @classmethod
    def is_same_position_group(cls, pos1: str, pos2: str) -> bool:
        """Checks if two position codes belong to the same positional subgroup for Yellow grading."""
        if pos1 == pos2:
            return True
        for group in POSITION_SUBGROUPS:
            if pos1 in group and pos2 in group:
                return True
        return False

    @classmethod
    def compare_attributes(
        cls,
        target: WeddlePlayer,
        guessed: WeddlePlayer,
    ) -> WeddleComparisonAttributes:
        """
        Compares guessed player against the target player across all 8 dimensions:
        - Team: green (exact) / gray
        - Side of Ball: green (exact) / gray
        - Position: green (exact) / yellow (sub-group) / gray
        - Conference: green (exact) / gray
        - Division: green (exact) / gray
        - Age: green (exact) / yellow (within ±2 years) / gray (with higher/lower direction)
        - Height: green (exact) / yellow (within ±2 inches) / gray (with higher/lower direction)
        - Jersey Number: green (exact) / yellow (within ±2) / gray (with higher/lower direction)
        """
        # 1. Team
        team_status = "green" if guessed.team == target.team else "gray"

        # 2. Side of Ball
        side_status = "green" if guessed.side_of_ball == target.side_of_ball else "gray"

        # 3. Position
        if guessed.position == target.position:
            pos_status = "green"
        elif cls.is_same_position_group(guessed.position, target.position):
            pos_status = "yellow"
        else:
            pos_status = "gray"

        # 4. Conference
        conf_status = "green" if guessed.conference == target.conference else "gray"

        # 5. Division
        div_status = "green" if guessed.division == target.division else "gray"

        # 6. Age (strictly evaluated dynamically)
        if guessed.age == target.age:
            age_status = "green"
            age_dir = None
        else:
            age_status = "yellow" if abs(guessed.age - target.age) <= 2 else "gray"
            age_dir = "higher" if target.age > guessed.age else "lower"

        # 7. Height
        if guessed.height_inches == target.height_inches:
            height_status = "green"
            height_dir = None
        else:
            height_status = "yellow" if abs(guessed.height_inches - target.height_inches) <= 2 else "gray"
            height_dir = "higher" if target.height_inches > guessed.height_inches else "lower"

        # 8. Jersey Number
        if guessed.jersey_number == target.jersey_number:
            jersey_status = "green"
            jersey_dir = None
        else:
            jersey_status = "yellow" if abs(guessed.jersey_number - target.jersey_number) <= 2 else "gray"
            jersey_dir = "higher" if target.jersey_number > guessed.jersey_number else "lower"

        return WeddleComparisonAttributes(
            team=AttributeComparison(status=team_status, direction=None),
            side_of_ball=AttributeComparison(status=side_status, direction=None),
            position=AttributeComparison(status=pos_status, direction=None),
            conference=AttributeComparison(status=conf_status, direction=None),
            division=AttributeComparison(status=div_status, direction=None),
            age=AttributeComparison(status=age_status, direction=age_dir),
            height=AttributeComparison(status=height_status, direction=height_dir),
            jersey_number=AttributeComparison(status=jersey_status, direction=jersey_dir),
        )

    @classmethod
    def evaluate_guess(
        cls,
        target: WeddlePlayer,
        guessed: WeddlePlayer,
        previous_guesses: Optional[List[str]] = None,
    ) -> WeddleGuessResponse:
        """
        Evaluates a guess submission against the target mystery player.
        Computes remaining guesses (max 6), is_game_over, and conditionally reveals target.
        """
        prev = previous_guesses or []
        guess_number = len(prev) + 1
        guesses_remaining = max(0, 6 - guess_number)

        is_correct = (
            guessed.player_id == target.player_id
            or guessed.full_name.lower().strip() == target.full_name.lower().strip()
        )

        comparison_attrs = cls.compare_attributes(target=target, guessed=guessed)

        # If guess is exact, ensure all attributes reflect green
        if is_correct:
            comparison_attrs = WeddleComparisonAttributes(
                team=AttributeComparison(status="green", direction=None),
                side_of_ball=AttributeComparison(status="green", direction=None),
                position=AttributeComparison(status="green", direction=None),
                conference=AttributeComparison(status="green", direction=None),
                division=AttributeComparison(status="green", direction=None),
                age=AttributeComparison(status="green", direction=None),
                height=AttributeComparison(status="green", direction=None),
                jersey_number=AttributeComparison(status="green", direction=None),
            )

        is_game_over = is_correct or (guesses_remaining == 0)
        revealed_target = target if is_game_over else None

        return WeddleGuessResponse(
            is_correct=is_correct,
            guesses_remaining=guesses_remaining,
            is_game_over=is_game_over,
            comparison=WeddleGuessComparison(
                player=guessed,
                attributes=comparison_attrs,
            ),
            revealed_target=revealed_target,
        )
