# mothersauce

## NAME

mothersauce - an example command: a pet you can feed and play with

## SYNOPSIS

```
mothersauce [--version] [command] [options]
mothersauce status [--name NAME] [--json]
mothersauce feed [--times N] [--name NAME] [--json]
mothersauce play [--times N] [--name NAME] [--json]
mothersauce guide
mothersauce man [--install | --raw]
```

## DESCRIPTION

`mothersauce` is the example command that ships with python-package-template. It keeps a pet whose state is two
numbers from 0 to 10: hunger, where 0 is full, and happiness, where 10 is happy. It exists to show the conventions a
command made from the template follows, so replace it with your own once you have renamed the package.

The conventions: every command prints a sentence for people and JSON with `--json`; `guide` prints this manual for
people and agents alike; `man` shows the same text as a man page; exit status 0 means success.

With no command, `mothersauce` runs `status`.

## COMMANDS

| Command | What it does |
| --- | --- |
| `status` | Show the pet as it starts: hunger 5, happiness 5. |
| `feed` | Lower hunger by one per feed, never below 0, then show the pet. |
| `play` | Raise happiness by one per game, never above 10, then show the pet. |
| `guide` | Print this manual as Markdown. |
| `man` | Show the man page. `--install` puts it where `man mothersauce` finds it; `--raw` prints roff. |

## OPTIONS

| Option | Meaning |
| --- | --- |
| `--name NAME` | The pet's name. Default: Baby Python. |
| `--times N` | How many times to feed or play, 1 to 10. Default: 1. |
| `--json` | Print one JSON object instead of a sentence. |
| `--version` | Print the version and exit. |
| `--help` | Print the options of a command and exit. |

## JSON OUTPUT

`status`, `feed` and `play` print one object with three fields:

```
{"name": "Baby Python", "hunger": 4, "happiness": 5}
```

`name` is a string; `hunger` and `happiness` are integers from 0 to 10.

## EXIT STATUS

0 on success. 2 when the arguments are wrong, with the reason on standard error.

## FILES

`~/.local/share/man/man1/mothersauce.1` is where `man --install` writes the man page, or
`$XDG_DATA_HOME/man/man1/` when that variable is set.

## EXAMPLES

Feed the pet three times and read the result as JSON:

```
mothersauce feed --times 3 --json
```

Install the man page, then read it:

```
mothersauce man --install
man mothersauce
```

## FOR AGENTS

Run commands with `--json` and parse the object; the fields are stable. `mothersauce guide` returns this whole
manual, so an agent can learn the command without browsing. Nothing here touches the network or the disk, except
`man --install`, which writes one file in the user's man folder.

## SEE ALSO

The template and its checks: https://github.com/jpsanders/python-package-template

## AUTHOR

James Phillip Sanders, https://jamesphillipsanders.com
