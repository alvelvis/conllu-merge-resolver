import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
import sys
import os
import re

def show_dialog_close(message):
    md = Gtk.MessageDialog(window, 0, Gtk.MessageType.INFO, Gtk.ButtonsType.CLOSE, message)
    md.run()
    md.destroy()

def load_file(file):
    with open(file) as f:
        text = f.read()
        if not '<<<<<<< HEAD' in text:
            show_dialog_close("File does not have Git conflict markers.")
            return
        window.corpus = text.split("\n\n")
    window.filename = file
    window.solved = {}
    objects['filename'].set_text(window.filename)
    window.tokens = {}
    for i, sentence in enumerate(window.corpus):
        window.tokens[i] = {}
        for token in sentence.splitlines():
            if len(token.split("\t")) == 10:
                window.tokens[i][token.split("\t")[0]] = token.split("\t")[1]
    count_conflicts()
    goto_conflict(0)

def count_conflicts():
    good_conflicts = list(filter(lambda i: "=======" in window.corpus[i] and len(window.corpus[i].split("<<<<<<< HEAD")) == len(window.corpus[i].split('>>>>>>> ')), range(len(window.corpus))))
    bad_conflicts = len(list(filter(lambda i: "=======" in window.corpus[i] and len(window.corpus[i].split("<<<<<<< HEAD")) != len(window.corpus[i].split('>>>>>>> ')), range(len(window.corpus)))))
    window.conflicts = []
    window.conflicts_i = {}
    window.conflicts_l = {}
    n = 0
    for i in good_conflicts:
        inside_head = False
        inside_incoming = False
        for l, line in enumerate(window.corpus[i].splitlines()):
            if line.startswith("<<<<<<< HEAD"):
                inside_head = True
                start = l
                head = []
                continue
            if line.startswith("======="):
                inside_head = False
                inside_incoming = True
                incoming = []
                continue
            if line.startswith(">>>>>>>"):
                inside_incoming = False
                if len(head) == len(incoming) and all(len(x.split("\t")) == 10 for x in head + incoming):
                    incoming_branch = line.split(">>>>>>>")[1].split()[0].strip()
                    conflict = {}
                    conflict['incoming_branch'] = incoming_branch
                    end = l
                    window.conflicts_l[(i, start, end)] = []
                    for t in range(len(head)):
                        conflict['head'] = head[t]
                        conflict['incoming'] = incoming[t]
                        window.conflicts.append(dict(conflict.items()))
                        window.conflicts_i[n] = i
                        window.conflicts_l[(i, start, end)].append(n)
                        n += 1
                else:
                    bad_conflicts += 1
                continue
            if inside_head:
                head.append(line)
            if inside_incoming:
                incoming.append(line)
    objects['unsolvable_conflicts'].set_text("{} unsolvable conflicts".format(bad_conflicts))
    objects['conflicts'].set_text("{} conflicts".format(len(window.conflicts)))

def goto_conflict(n):
    window.this_conflict = n
    objects['this_conflict'].set_text("Now: {}".format(n+1))
    objects['solved_conflicts'].set_text("{} solved conflicts".format(len(window.solved)))
    if objects['sentence'].get_text(objects['sentence'].get_start_iter(), objects['sentence'].get_end_iter(), True) != window.corpus[window.conflicts_i[n]]:
        objects['sentence'].set_text(window.corpus[window.conflicts_i[n]])
    objects['token_in_conflict'].set_label(window.conflicts[n]['incoming'] if not n in window.solved else window.solved[n])
    text_word_id = window.conflicts[n]['incoming'].split("\t")[0]
    text_word = window.conflicts[n]['incoming'].split("\t")[1]
    text_left = [y for x, y in window.tokens[window.conflicts_i[n]].items() if not '-' in x and int(x) < int(text_word_id)]
    text_right = [y for x, y in window.tokens[window.conflicts_i[n]].items() if not '-' in x and int(x) > int(text_word_id)]
    objects['text_word'].set_text(text_word)
    objects['text_left'].set_text(" ".join(text_left))
    objects['text_right'].set_text(" ".join(text_right))
    objects['incoming_branch'].set_text(window.conflicts[n]['incoming_branch'])
    if n in window.solved:
        objects['token_in_conflict'].get_style_context().add_class("conflict-solved")
    else:
        objects['token_in_conflict'].get_style_context().remove_class("conflict-solved")
    for i, col in enumerate(cols.split()):
        objects['left_{}'.format(col)].set_label(window.conflicts[n]['head'].split("\t")[i])
        objects['right_{}'.format(col)].set_label(window.conflicts[n]['incoming'].split("\t")[i])
        if window.conflicts[n]['head'].split("\t")[i] != window.conflicts[n]['incoming'].split("\t")[i]:
            objects['left_{}'.format(col)].get_style_context().add_class("conflict")
            objects['right_{}'.format(col)].get_style_context().add_class("conflict")
        else:
            objects['left_{}'.format(col)].get_style_context().remove_class("conflict")
            objects['right_{}'.format(col)].get_style_context().remove_class("conflict")
    objects['left_label'].set_text('dephead ({})'.format(window.tokens[window.conflicts_i[n]].get(window.conflicts[n]['head'].split("\t")[6], "None")))
    objects['right_label'].set_text('dephead ({})'.format(window.tokens[window.conflicts_i[n]].get(window.conflicts[n]['incoming'].split("\t")[6], "None")))

def click_button(btn):
    button = Gtk.Buildable.get_name(btn)
    
    if button == "open_file":
        win = FileChooserWindow()
        if win.filename:
            load_file(win.filename)
        return

    if button == "next_conflict":
        if len(window.conflicts) > window.this_conflict -1:
            if not window.this_conflict in window.solved:
                show_dialog_close("Conflict not solved.")
            goto_conflict(window.this_conflict +1)
        return

    if button == "previous_conflict":
        if window.this_conflict:
            goto_conflict(window.this_conflict -1)
        return

    if button == "copy_from_left":
        for col in cols.split():
            change_col(objects["left_{}".format(col)])
        goto_conflict(window.this_conflict + 1)
        return

    if button == "copy_from_right":
        for col in cols.split():
            change_col(objects["right_{}".format(col)])
        goto_conflict(window.this_conflict + 1)
        return

    if button == "save_changes":
        saved = 0
        for l in sorted(window.conflicts_l, key=lambda x: (x[0], -x[1])):
            if all(n in window.solved for n in window.conflicts_l[l]):
                i = l[0]
                start = l[1]
                end = l[2]
                sentence = window.corpus[i].splitlines()
                del sentence[start:end+1]
                for n in reversed(window.conflicts_l[l]):
                    sentence.insert(start, window.solved[n])
                window.corpus[i] = "\n".join(sentence)
                saved += 1
                print(window.corpus[i])
        show_dialog_close("{} conflicts were fixed and saved to \"{}\".".format(saved, window.filename))
        exit()

def change_col(btn):
    col = Gtk.Buildable.get_name(btn).split("_")[1]
    c = cols.split().index(col)
    token_in_conflict = objects['token_in_conflict'].get_label().split("\t")
    token_in_conflict[c] = btn.get_label()
    objects['token_in_conflict'].set_label("\t".join(token_in_conflict))
    objects['token_in_conflict'].get_style_context().add_class("conflict-solved")
    window.solved[window.this_conflict] = "\t".join(token_in_conflict)
    return

class FileChooserWindow(Gtk.Window):
    def __init__(self):
        dialog = Gtk.FileChooserDialog(
            title="Please choose a CoNLL-U file", parent=window, action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,
            Gtk.ResponseType.OK,
        )

        self.add_filters(dialog)

        response = dialog.run()
        
        if response == Gtk.ResponseType.OK:
            self.filename = dialog.get_filename()
        elif response == Gtk.ResponseType.CANCEL:
            self.filename = ""
        
        dialog.destroy()

    def add_filters(self, dialog):
        filter_conllu = Gtk.FileFilter()
        filter_conllu.set_name("CoNLL-U files (*.conllu)")
        filter_conllu.add_pattern("*.conllu")
        dialog.add_filter(filter_conllu)

builder = Gtk.Builder()
builder.add_from_file("conllu-merge-resolver.glade")
screen = Gdk.Screen.get_default()
provider = Gtk.CssProvider()
provider.load_from_path("conllu-merge-resolver.css")
Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

buttons = "text_word text_left text_right open_file next_conflict previous_conflict copy_from_left copy_from_right token_in_conflict save_changes filename conflicts this_conflict solved_conflicts unsolvable_conflicts sentence left_label right_label incoming_branch"
cols = "id word lemma upos xpos feats dephead deprel deps misc"

objects = {
    x: builder.get_object(x)
    for x in buttons.split()
}

for button in buttons.split():
    if isinstance(objects[button], Gtk.Button):
        objects[button].connect('clicked', click_button)

for col in cols.split():
    for direction in ["left", "right"]:
        objects["{}_{}".format(direction, col)] = builder.get_object("{}_{}".format(direction, col))
        objects["{}_{}".format(direction, col)].connect('clicked', change_col)

window = builder.get_object("window1")
window.connect("destroy", Gtk.main_quit)
window.show_all()

if len(sys.argv) > 1:
    if not os.path.isfile(sys.argv[1]):
        show_dialog_close("Files \"{}\" does not exist.".format(sys.argv[1]))
        exit()
    else:
        load_file(sys.argv[1])

if __name__ == "__main__":
    Gtk.main()
