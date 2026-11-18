# Lore notes for MOOSE MAN.  style: 'typed' (courier) or 'hand' (handwriting)

NOTES = {
    "flyer": ("Missing Person Flyer", "typed", """MISSING

KYLE ANDREW BRANDT
Age 14  -  5'4"  -  Brown hair

Last seen September 9, 2003, riding his bike
near the Hollins Road trailhead. He was wearing
a red Millbrook Hornets hooded sweatshirt.

If you have ANY information please call the
Harlan County Sheriff's Office.

PLEASE. WE JUST WANT HIM HOME.


(someone has written along the bottom in pen:)
the moose man took him. he took him under."""),

    "notebook": ("Notebook Page", "hand", """Oct 4 2003

Me, Jamie and Trev came out here to see if the Moose Man stuff was real. Trev's brother says Kyle went into the big drain by the creek because somebody dared him.

We heard something walking around the fire for like an hour. On two legs. But heavy. Like hooves on rocks.

Trev shined the flashlight at it and it just stood there between the trees. It was too tall. Its head was wrong. It didn't blink.

Trev dropped the light and we ran. We left everything.

Jamie says he's going back for Kyle. I told him he's stupid.

I'm not coming back here. I'm never coming back here."""),

    "sign": ("County Sign", "typed", """HARLAN COUNTY PUBLIC WORKS

HOLLINS CREEK STORM OUTFALL #7
OVERFLOW SYSTEM "C"

DANGER - NO ENTRY
Confined space. Flash flooding.
Trespassers will be prosecuted.


(scratched into the paint below, deep, with something sharp:)

HE LIVES IN THE DARK PART"""),

    "pwlog": ("Inspection Log", "typed", """PUBLIC WORKS - INSPECTION LOG
Outfall #7 / Overflow System C
Inspector: R. Okafor

03/12/1998 - Debris blockage at junction. Cleared.
Large amounts of animal hair caught in the grates.
Coarse. Brown. Smells like a barn.

03/19/1998 - Blockage again. Bones in it this time.
Deer, probably. Some of them cut very clean.
A boot. Size 9.

03/26/1998 - Heard something moving in Chamber C.
Supervisor says raccoons.
Raccoons don't breathe like that.

04/02/1998 - It was standing at the end of the
gallery when my light came back on. It was
wearing a moose head. I watched it tilt its head
like a dog does when it hears its name.

I am requesting a transfer. I am not going back
down there without the sheriff."""),

    "memo": ("Maintenance Memo", "typed", """MEMO - 06/14/2001
TO: Overflow System C staff

Chamber C continues to flood. The primary drain
gate is seized and the county will not fund repair.

Until further notice Chamber C must be drained
MANUALLY by opening ALL FIVE relief valves:

   1. Cistern (west)
   2. Pump Room
   3. Valve Office (back room)
   4. Old Holding Room (north)
   5. East Overflow

The service ladder to the surface is on the far
side of Chamber C. There is no other way out.

Do NOT work alone down here.
Do NOT leave the lights off.
Do NOT go into the holding room.

- D. Whitcomb, Supervisor"""),

    "journal1": ("Journal of Dale Ruckert (I)", "hand", """Nov 2, 1987

Shot the white bull at dawn down by the creek. Never in my life seen one like it. Pure white. Eyes like pink glass. It didn't run. It just stood there looking at me like it knew my name.

Took three shots to put it down. It made a sound I won't ever forget. That wasn't a moose sound. That was a man sound.

Took the head and the hide. Gonna have it mounted. Linda will hate it.

Storm came in fast and I lost the trail. Took shelter in the big county drain by the creek. Plenty dry further in.

I'll head home in the morning."""),

    "journal2": ("Journal of Dale Ruckert (II)", "hand", """Nov ?? 1987

Cold. So cold down here. Can't find the way I came in. All the tunnels look the same.

Wore the hide like a coat. Put the head on for the warmth. It's warm in there. Warmer than it should be. Like something is still alive in it.

I hear breathing when I sleep. Big slow breathing. I think it's mine.

Tried to climb out today. The light hurt my eyes so bad I came back down.

I'm hungry all the time now. Not for the jerky.

The head talks to me in my father's voice. It says a herd has to be big to be safe."""),

    "journal3": ("Journal of Dale Ruckert (III)", "hand", """it doesnt come off

i pulled until my fingers came apart and it doesnt come off. there is no seam anymore. there is no inside and outside. my face went INTO it

i am taller now
i am so tall

the herd is lonely. i bring them down and i fix them so they stand still and quiet like good ones. i give them antlers so they look like me. so they belong

linda if anybody gives you this dont come looking

dont look at me
it knows when you look at it"""),

    "kyle": ("Note, scratched on a cereal box", "hand", """my name is kyle brandt i am 14

he brings us down here. he puts sticks on our heads so we look like him

if you move he fixes you. i saw him fix a man. i saw him

there is a boy named jamie here now he wont stop crying. i told him stand still

i can hear it walking in the water. the hooves click

if somebody finds this tell my mom im sorry i went in the drain. tell her i was brave

tell her i stood still"""),

    "report": ("Sheriff's Report", "typed", """HARLAN COUNTY SHERIFF'S DEPARTMENT
INCIDENT REPORT #87-1144  (SUPPLEMENT, 1989)

SUBJECT: RUCKERT, DALE E.
STATUS:  Missing since 11/02/1987

Search of Outfall #7 overflow system suspended
following injury to Deputy M. Hale.

Deputy Hale described his assailant as "a very
tall man wearing the head of a moose."

When asked to clarify, Deputy Hale stated:
"He wasn't wearing it."

Deputy Hale has been placed on medical leave.
Deputy Hale has not stopped talking about the
way it stood still.

Per Sheriff Dunn: CASE CLOSED.
Overflow System C to be sealed.
DO NOT RELEASE TO PRESS."""),

    "jamie": ("Note, wet and torn", "hand", """oct 2003

i found kyle. hes in the holding room standing with the others. hes so thin. his eyes are open

i tried to pull the branches off his head and they are grown in. they are GROWN IN

i hear it coming back. its walking in the water

im going to hide in the deep part. it cant smell you under the water

it cant

it"""),
}

NOTE_ORDER = ["flyer", "notebook", "sign", "pwlog", "memo", "report", "journal1",
              "journal2", "kyle", "journal3", "jamie"]

INTRO_TEXT = [
    "OCTOBER 31, 2003  -  11:58 PM",
    "HOLLINS WOODS, HARLAN COUNTY",
    "",
    "Three kids have gone missing near these woods since August.",
    "Everyone in Millbrook has heard about the Moose Man.",
    "",
    "Nobody has ever filmed him.",
    "",
    "You brought the old lantern from the garage and your dad's camcorder.",
    "Tonight you're going to prove he's real.",
]

CONTROLS_TEXT = [
    "WASD - move      MOUSE - look      SHIFT - run      CTRL / C - crouch",
    "F - lantern      E - interact (hold to turn valves)      Q - objective      TAB - backpack      ESC - pause",
]

CH2_WAKE_LINES = [
    (8.0, "The stove is out. You can see your breath.", 4.0),
    (11.0, "A snowstorm is coming in tonight.", 4.0),
    (14.0, "You need firewood. A lot of it.", 4.0),
]

CH3_WAKE_LINES = [
    (4.2, "The fire's going out.", 3.5),
    (8.6, "A blizzard. The snow outside is up to your knees.", 3.0),
    (11.4, "It isn't safe here anymore.", 3.0),
    (15.0, "A cave. Out of the wind, at least.", 3.4),
    (26.6, "Hide.", 2.0),
]

CH3_ENDING = [
    [
        "You come out of the mountain into the white.",
        "",
        "You don't stop running until you see the concrete mouth",
        "of the storm drain, half buried in snow.",
        "",
        "It was safe down there once.",
        "It has to be.",
    ],
]

CH4_OPEN_LINES = [
    (4.0, "Back in the drain. Back where it started.", 3.2),
    (7.0, "The Goat Man ate him. He's dead. It's safe down here.", 3.4),
    (11.2, "No.", 1.6),
    (12.8, "I watched him die.", 2.4),
    (16.0, "What is he doing", 2.4),
    (27.5, "...", 1.5),
    (30.0, "He got up.", 2.0),
    (32.6, "It's so much bigger down here.", 3.0),
]

CH4_ENDING = [
    [
        "The gate shuts behind you.",
        "",
        "It is warmer on this side. The air moves,",
        "like something very big is breathing somewhere ahead.",
        "",
        "Behind the bars, he doesn't follow.",
        "",
        "He just watches you go.",
    ],
]

CH5_ENDING = [
    [
        "It is morning.",
        "",
        "The snow has stopped. The sun is coming up over Hollins Woods,",
        "and somewhere below you a road is running toward town.",
        "",
        "Behind you, in the dark, nothing moves.",
        "",
        "For the first time in four days, nothing is following you.",
    ],
    [
        "END OF CHAPTER FIVE",
        "",
        "",
        "M O O S E   M A N",
        "",
        "thank you for playing",
    ],
]

CH2_ENDING = [
    [
        "You don't sleep.",
        "",
        "The wind comes in through the broken window all night.",
        "",
        "Out in the snow, something white is still moving between the trees.",
        "",
        "It walks on its hands.",
    ],
    [
        "END OF CHAPTER TWO",
        "",
        "",
        "M O O S E   M A N",
        "",
        "CHAPTER THREE  -  coming soon",
        "",
        "thank you for playing",
    ],
]

ENDING_PAGES = [
    [
        "4:19 AM.  Route 9.",
        "",
        "The car never stopped.",
        "",
        "Whatever it hit got up again,",
        "and went back into the trees.",
        "",
        "It looked at you first.",
    ],
    [
        "HARLAN COUNTY REGISTER  -  November 3, 2003",
        "",
        "A motorist traveling Route 9 early Saturday reported striking",
        "\"a deer, or something standing up like a man\" near mile marker 14.",
        "",
        "No animal was recovered.",
        "",
        "Deputies found two sets of tracks at the scene. One led into",
        "Hollins Woods. The other ended at the shoulder of the road,",
        "beside the partially eaten remains of a second animal.",
        "",
        "Its skull has been sent to the state lab.",
        "Its antlers have not been found.",
    ],
    [
        "END OF CHAPTER ONE",
        "",
        "",
        "M O O S E   M A N",
        "",
        "Something bigger lives in Hollins Woods.",
        "",
        "CHAPTER TWO  -  coming soon",
        "",
        "thank you for playing",
    ],
]
