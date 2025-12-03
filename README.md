# THF Cue Planner

A timeline system for museums and AV-heavy immersive experiences, built to stop chaos, soothe project managers, and reduce the average number of late-night WhatsApp messages from contractors.

This tool is designed for people who want timelines that make sense, PDF reports that don’t look like crime-scene photos, and a workflow that doesn’t require sacrificing a projector lamp to the gods of scheduling.

## What This Does
### Room-by-Room Cue Editing

Each room receives its own dedicated tab, allowing you to:

- Add cues with names, cue types, trigger types, play behaviours, start modes, and notes

Define when things start using:

- AT_TIME

- AFTER_PREVIOUS

- AFTER_CUE

- Assign dependencies between cues

- Cleanly view all cues in a table

- See them visualised on a per-room timeline with lane separation to prevent overlaps

- Full Timeline Visualisation

Every room includes a timeline that:

- Automatically creates lanes for overlapping cues

- Keeps labels readable

- Supports zooming and panning

- Uses a consistent colour scheme so you can spot cue types instantly

## Mega Summary

The Summary Tab combines all rooms into:

- A fully stitched global timeline (Reception → Mecca)

- tatistics per cue type, trigger type, playback mode

- Room-by-room durations and breakdowns

- Notes, operator guidance, and a complete human-readable timeline dump

This is the place where you finally see the whole show from beginning to end without losing your will to live.

## PDF Export

Exporting a professional PDF is as simple as pressing one button. The system generates:

- A global stitched Gantt that auto-scales to fill the entire first page

- A separate page per room, each with its own cleanly scaled timeline

- A full, neatly formatted text report, with headings styled for clarity

These graphs are generated from scratch using ReportLab, ensuring consistent sizing, no microscopic bars, and no dependency on the GUI’s zoom or scale.

You get a document you can actually hand to a client without apologising.

How Cue Dependencies Work
- AT_TIME

- Cue begins at a specified timestamp. Perfect for exact timing or compulsive planners.

- AFTER_PREVIOUS

- Cue starts immediately after the one before it. Useful for simple sequences.

- AFTER_CUE

Cue waits until another specific cue finishes, no matter where it sits in the list.
Excellent for tightly choreographed AV events or avoiding synchronisation disasters.

Features Designed For Real Life
Multi-lane Rendering

Cue bars never overlap. They stack neatly, like well-behaved children in a school photo.

Auto-Scaling

Whether you have 20 cues or 200, the graphs expand or contract to remain readable.

JSON Import/Export

Save work, load work, move work between computers, or restore things after one accidental deletion too many.

Dark Theme Interface

Easier on the eyes during late-night programming sessions on-site.

Requirements

Python 3.x

PyQt5

ReportLab

A functioning brain cell (optional but encouraged)

Install dependencies with:

pip install PyQt5 reportlab

How to Run
python main.py


If it doesn’t launch:

Verify your Python installation

Reinstall the dependencies

Reboot your computer

Offer motivational words to your GPU

Why This Exists

Anyone who has worked on a museum, immersive room, or AV-heavy installation knows:

The timelines never arrive on time

The cue lists contradict each other

Half the details live inside someone's WhatsApp messages

The planner changes every three hours

No one knows how long anything actually lasts

This tool fixes all of that by becoming the one source of truth.
A timeline you can trust. A PDF you can hand to the client. A system that lets you sleep better at night.

Final Thoughts

This planner was created for real-world projects: tight deadlines, shifting contractor schedules, changing designs, last-minute requests, truss work, missed cable pulls, and everything else that turns installations into heroic sagas.

Use it well, generate good PDFs, and above all:

Stop making timelines in Excel.
