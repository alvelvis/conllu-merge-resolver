import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
import sys
import os
import estrutura_ud
import interrogar_UD

def show_dialog_close(message, entry=False):
    md = Gtk.MessageDialog(window, 0, Gtk.MessageType.INFO, Gtk.ButtonsType.CLOSE, message)
    if entry:
        md.userEntry = Gtk.Entry()
        md.userEntry.set_size_request(250,0)
        md.get_content_area().pack_end(md.userEntry, False, False, 0)
    md.show_all()
    md.run()
    if entry:
        window.userEntry = md.userEntry.get_text()
    md.destroy()    

def load_file(kind, file, file2="", query=""):
    with open(file) as f:
        text = f.read()
    if kind == "git":
        if not '<<<<<<< HEAD' in text:
            show_dialog_close("File does not have Git conflict markers.")
            return
        window.kind = "git"
    window.corpus = text.split("\n\n")
    if kind == "confusion":
        with open(file2) as f:
            text2 = f.read()
        window.corpus2 = text2.split("\n\n")
        window.kind = "confusion"
    window.filename = file
    window.filename2 = file2
    window.solved = {}
    objects['filename'].set_text(window.filename)
    objects['filename2'].set_text(window.filename2)
    window.tokens = {}
    for i, sentence in enumerate(window.corpus):
        window.tokens[i] = {}
        for token in sentence.splitlines():
            if len(token.split("\t")) == 10:
                window.tokens[i][token.split("\t")[0]] = token.split("\t")[1]
    count_conflicts(query=query)
    if not window.conflicts:
        show_dialog_close("No conflicts were found.")
        exit()
    goto_conflict(0)

def count_conflicts(query):
    if window.kind == "git":
        good_conflicts = list(filter(lambda i: "=======" in window.corpus[i] and len(window.corpus[i].split("<<<<<<< HEAD")) == len(window.corpus[i].split('>>>>>>> ')), range(len(window.corpus))))
        bad_conflicts = len(list(filter(lambda i: "=======" in window.corpus[i] and len(window.corpus[i].split("<<<<<<< HEAD")) != len(window.corpus[i].split('>>>>>>> ')), range(len(window.corpus)))))
    if window.kind == "confusion":
        confusions = interrogar_UD.main(window.filename, 5, query.replace("'", '"'))['output']
        good_conflicts = [[i for i, x in enumerate(window.corpus) if "# sent_id = {}\n".format(y['resultadoEstruturado'].sent_id) in x][0] for y in confusions]
        bad_conflicts = 0
        tokens_query = {}
        for result in confusions:
            tokens_query[result['resultadoEstruturado'].sent_id] = []
            for token in result['resultadoAnotado'].tokens:
                if "@BOLD" in token.to_str():
                    tokens_query[result['resultadoEstruturado'].sent_id].append((token.id.split("/")[1] if '/' in token.id else token.id).replace("@BOLD", ""))
    window.conflicts = []
    window.conflicts_i = {}
    window.conflicts_l = {}
    n = 0
    for i in good_conflicts:
        if window.kind == "confusion":
            sent_id = window.corpus[i].split("# sent_id = ")[1].split("\n")[0]
            challenger = [x for i, x in enumerate(window.corpus2) if "# sent_id = {}\n".format(sent_id) in x]
            if not challenger:
                continue
            challenger = challenger[0]
            if len(list(filter(lambda x: len(x.split("\t")) == 10, window.corpus[i].splitlines()))) != len(list(filter(lambda x: len(x.split("\t")) == 10, challenger.splitlines()))):
                continue
            head = {}
            incoming = {}
            for l, line in enumerate(window.corpus[i].splitlines()):
                if line.split("\t")[0] in tokens_query[sent_id]:
                    head[line.split("\t")[0]] = (l, line)
            for l, line in enumerate(challenger.splitlines()):
                if line.split("\t")[0] in tokens_query[sent_id]:
                    incoming[line.split("\t")[0]] = (l, line)
            for token_id in incoming:
                if token_id in head and any(head[token_id][1].split("\t")[x] != incoming[token_id][1].split("\t")[x] for x in [cols.split().index(y) for y in cols.split()]):
                    conflict = {}
                    conflict['incoming_branch'] = ""
                    conflict['incoming'] = incoming[token_id][1]
                    conflict['head'] = head[token_id][1]
                    window.conflicts.append(dict(conflict.items()))
                    window.conflicts_i[n] = i
                    window.conflicts_l[(i, incoming[token_id][0], incoming[token_id][0])] = [n]
                    n += 1
        if window.kind == "git":
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
                    if all(len(x.split("\t")) == 10 for x in head + incoming) and [x.split("\t")[1] for x in head] == [x.split("\t")[1] for x in incoming]:
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
    if objects['sentence'].get_text(objects['sentence'].get_start_iter(), objects['sentence'].get_end_iter(), True) != window.corpus[window.conflicts_i[n]]:
        objects['sentence'].set_text(window.corpus[window.conflicts_i[n]])
    objects['token_in_conflict'].set_text(window.conflicts[n]['head'] if not n in window.solved else window.solved[n])
    text_word_id = window.conflicts[n]['incoming'].split("\t")[0]
    text_word = window.conflicts[n]['incoming'].split("\t")[1]
    text_left = [y for x, y in window.tokens[window.conflicts_i[n]].items() if not '-' in x and int(x) < int(text_word_id)] if not '-' in text_word_id else ""
    text_right = [y for x, y in window.tokens[window.conflicts_i[n]].items() if not '-' in x and int(x) > int(text_word_id)] if not '-' in text_word_id else ""
    objects['text_word'].set_text(text_word)
    objects['text_left'].set_text(" ".join(text_left))
    objects['text_right'].set_text(" ".join(text_right))
    if window.kind == "git":
        objects['filename2'].set_text(window.conflicts[n]['incoming_branch'])
    if n in window.solved:
        objects['token_in_conflict'].get_style_context().add_class("conflict-solved")
    else:
        objects['token_in_conflict'].get_style_context().remove_class("conflict-solved")
    for i, col in enumerate(cols.split()):
        objects['left_{}'.format(col)].set_label(window.conflicts[n]['head'].split("\t")[i])
        objects['right_{}'.format(col)].set_label(window.conflicts[n]['incoming'].split("\t")[i])
        objects['left_{}'.format(col)].get_style_context().remove_class("conflict")
        objects['right_{}'.format(col)].get_style_context().remove_class("conflict")
        objects['left_{}'.format(col)].get_style_context().remove_class("solved")
        objects['right_{}'.format(col)].get_style_context().remove_class("solved")
        if window.conflicts[n]['head'].split("\t")[i] != window.conflicts[n]['incoming'].split("\t")[i]:
            objects['right_{}'.format(col)].get_style_context().add_class("conflict")
            objects['left_{}'.format(col)].get_style_context().add_class("conflict")
    objects['left_label'].set_text('dephead ({})'.format(window.tokens[window.conflicts_i[n]].get(window.conflicts[n]['head'].split("\t")[6], "None")))
    objects['right_label'].set_text('({}) dephead'.format(window.tokens[window.conflicts_i[n]].get(window.conflicts[n]['incoming'].split("\t")[6], "None")))

def click_button(btn):
    button = Gtk.Buildable.get_name(btn)
    
    if button == "open_git_file":
        win = FileChooserWindow()
        if win.filename:
            load_file("git", win.filename)
        return

    if button == "open_confusion":
        window.king = "confusion"
        show_dialog_close("First, pick the file you want to edit.")
        win = FileChooserWindow()
        if win.filename:
            show_dialog_close("Second, pick the file to which you are comparing it.")
            win2 = FileChooserWindow()
            if win.filename and win2.filename:
                show_dialog_close("Finally, type the query to find tokens in the center of the confusion.", True)
                query = window.userEntry.strip()
                if query:
                    load_file("confusion", win.filename, win2.filename, query)
        return

    if button == "next_conflict":
        save_token_in_conflict()
        if len(window.conflicts) -1 > window.this_conflict:
            goto_conflict(window.this_conflict +1)
        return

    if button == "previous_conflict":
        save_token_in_conflict()
        if window.this_conflict:
            goto_conflict(window.this_conflict -1)
        return

    if button == "save_changes":
        save_token_in_conflict()
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
        with open(window.filename, "w") as f:
            f.write("\n\n".join(window.corpus))
        show_dialog_close("{} conflicts were fixed and saved to \"{}\".".format(saved, window.filename))
        exit()

    if button == "skip":
        if window.this_conflict in window.solved:
            del window.solved[window.this_conflict]
        if len(window.conflicts) -1 > window.this_conflict:
            goto_conflict(window.this_conflict+1)
        return

def save_token_in_conflict(btn=None):
    if objects['token_in_conflict'].get_text().strip() and len(objects['token_in_conflict'].get_text().strip().split("\t")) == 10:
        window.solved[window.this_conflict] = objects['token_in_conflict'].get_text()
        objects['token_in_conflict'].get_style_context().add_class("conflict-solved")
        objects['solved_conflicts'].set_text("{} solved conflicts".format(len(window.solved)))
    else:
        show_dialog_close("Conflict not solved.")
    sentence_text = objects['sentence'].get_text(objects['sentence'].get_start_iter(), objects['sentence'].get_end_iter(), True).strip()
    if sentence_text:
        window.corpus[window.conflicts_i[window.this_conflict]] = sentence_text

def change_col(btn):
    col = Gtk.Buildable.get_name(btn).split("_")[1]
    direction = Gtk.Buildable.get_name(btn).split("_")[0]
    c = cols.split().index(col)
    token_in_conflict = objects['token_in_conflict'].get_text().split("\t")
    token_in_conflict[c] = btn.get_label()
    objects['token_in_conflict'].set_text("\t".join(token_in_conflict))
    objects['{}_{}'.format(direction, col)].get_style_context().add_class("solved")
    objects['{}_{}'.format(direction, col)].get_style_context().remove_class("conflict")
    objects['{}_{}'.format('left' if direction == 'right' else 'right', col)].get_style_context().remove_class("solved")
    objects['{}_{}'.format('left' if direction == 'right' else 'right', col)].get_style_context().add_class("conflict")
    save_token_in_conflict()
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

buttons = "skip filename filename2 text_word text_left text_right open_git_file open_confusion next_conflict previous_conflict token_in_conflict save_changes filename conflicts this_conflict solved_conflicts unsolvable_conflicts sentence left_label right_label"
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

if len(sys.argv) == 2:
    if not os.path.isfile(sys.argv[1]):
        show_dialog_close("Files \"{}\" does not exist.".format(sys.argv[1]))
        exit()
    load_file("git", sys.argv[1])
if len(sys.argv) == 4:
    if not os.path.isfile(sys.argv[1]):
        show_dialog_close("Files \"{}\" does not exist.".format(sys.argv[1]))
        exit()
    if not os.path.isfile(sys.argv[2]):
        show_dialog_close("Files \"{}\" does not exist.".format(sys.argv[2]))
        exit()
    load_file("confusion", sys.argv[1], sys.argv[2], sys.argv[3])

if __name__ == "__main__":
    Gtk.main()
