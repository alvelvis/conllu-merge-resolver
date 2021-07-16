import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkSource', '3.0')
from gi.repository import Gtk, Gdk, GtkSource, GObject, GLib, Pango
from udapi.core.document import Document
from io import StringIO
import sys
import os
import json
import estrutura_ud
import interrogar_UD
import html
import git

def show_dialog_ok(message, entry=False):
    md = Gtk.MessageDialog(window, 0, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, message)
    if entry:
        md.userEntry = Gtk.Entry()
        md.userEntry.set_size_request(250,0)
        md.get_content_area().pack_end(md.userEntry, False, False, 0)
    md.show_all()
    md.run()
    if entry:
        window.userEntry = md.userEntry.get_text()
    md.destroy()
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

def load_file(kind, file, file2="", query=""):
    with open(file, encoding="utf-8") as f:
        text = f.read()
    if kind == "git":
        if not '<<<<<<< HEAD' in text:
            show_dialog_ok("File does not have Git conflict markers.")
            sys.exit()
        window.kind = "git"
    window.corpus = text.split("\n\n")
    window.corpus_i = {x.split("# sent_id = ")[1].split("\n")[0]: i for i, x in enumerate(window.corpus) if x.strip() and '# sent_id = ' in window.corpus[i]}
    if kind == "confusion":
        with open(file2, encoding="utf-8") as f:
            text2 = f.read()
        window.corpus2 = text2.split("\n\n")
        window.corpus2_i = {x.split("# sent_id = ")[1].split("\n")[0]: i for i, x in enumerate(window.corpus2) if x.strip() and '# sent_id = ' in window.corpus2[i]}
        window.kind = "confusion"
    window.filename = file
    window.filename2 = file2
    window.solved = {}
    branch = ""
    if os.path.dirname(os.path.abspath(window.filename)) != os.path.dirname(os.path.abspath(__file__)):
        try:
            repo = git.Repo(file, search_parent_directories=True)
            if repo:
                with open("{}/HEAD".format(repo.git_dir)) as f:
                    branch = f.read().strip().rsplit("/", 1)[1]
        except git.exc.InvalidGitRepositoryError:
            sys.stderr.write("No git repo found for this file.\n")
    objects['filename'].set_text("{}: {}{}".format(
        "Head" if kind == "git" else "Left", 
        os.path.basename(window.filename),
        " (branch: {})".format(branch) if branch else ""))
    objects['filename2'].set_text("{}: {}".format(
        "Right", 
        os.path.basename(window.filename2)) if kind == "confusion" else "")
    window.tokens = {}
    for i, sentence in enumerate(window.corpus):
        window.tokens[i] = {}
        for token in sentence.splitlines():
            id = token.split("\t")[0]
            if len(token.split("\t")) == 10 and not id in window.tokens[i]:
                window.tokens[i][id] = token
    count_conflicts(query=query)
    if not window.conflicts:
        show_dialog_ok("No conflicts were found.")
        sys.exit()
    window.unsaved = True
    window.this_conflict = 0
    goto_conflict(0)
    return

def count_conflicts(query):
    if window.kind == "git":
        good_conflicts = list(filter(lambda i: "=======" in window.corpus[i] and len(window.corpus[i].split("<<<<<<< HEAD")) == len(window.corpus[i].split('>>>>>>> ')), range(len(window.corpus))))
        bad_conflicts = len(list(filter(lambda i: "=======" in window.corpus[i] and len(window.corpus[i].split("<<<<<<< HEAD")) != len(window.corpus[i].split('>>>>>>> ')), range(len(window.corpus)))))
    if window.kind == "confusion":
        query = query.replace("'", '"')
        important_cols = query.split("{")[1].split("}")[0] if '{' in query else ",".join(cols.split())
        query = query.replace("{{{}}}".format(important_cols), "").strip()
        important_cols = important_cols.replace(" ", "").split(",")
        if not query:
            query = ".*"
        if not '".*"' in query and query != '.*':
            confusions = interrogar_UD.main(window.filename, 5, query)['output']
        else:
            confusions = []
            for sentence in window.corpus:
                if sentence.strip():
                    confusions.append({'resultadoAnotado': estrutura_ud.Sentence(), 
                        'resultadoEstruturado': estrutura_ud.Sentence()})
                    confusions[-1]['resultadoEstruturado'].build(sentence)
                    confusions[-1]['resultadoAnotado'].build(sentence)
                    for token in confusions[-1]['resultadoAnotado'].tokens:
                        token.id += "@BOLD"
        good_conflicts = sorted([window.corpus_i[y['resultadoEstruturado'].sent_id] for y in confusions])
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
            if sent_id in window.corpus2_i:
                challenger = window.corpus2[window.corpus2_i[sent_id]]
            else:
                continue
            if (len(list(filter(lambda x: len(x.split("\t")) == 10, window.corpus[i].splitlines()))) != 
            len(list(filter(lambda x: len(x.split("\t")) == 10, challenger.splitlines())))):
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
                if (token_id in head and 
                any(head[token_id][1].split("\t")[x] != incoming[token_id][1].split("\t")[x] for 
                x in [cols.split().index(y) for y in important_cols])):
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
                    if (all(len(x.split("\t")) == 10 for x in head + incoming) and 
                    [x.split("\t")[1] for x in head] == [x.split("\t")[1] for x in incoming]):
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
    window.conflicts_each_i = {
        i: list(filter(lambda n: window.conflicts_i[n] == i, range(len(window.conflicts))))
        for i in range(len(window.corpus))}
    window.conflicts_nav_label = {}
    window.token_in_conflict = ""
    position = 0
    for child in objects['conflicts_nav'].get_children():
        objects['conflicts_nav'].remove(child)
    if len(window.conflicts) < 2000:
        for i in window.conflicts_each_i:
            if window.corpus[i].strip() and window.conflicts_each_i[i]:
                position += 1
                sent_id = window.corpus[i].split("# sent_id = ")[1].split("\n")[0]
                label = Gtk.Label(
                    label=" {}".format(sent_id),
                    xalign=0)
                objects['conflicts_nav'].insert(label, -1)
                label.n = window.conflicts_each_i[i][0]
                for _i, _n in enumerate(window.conflicts_each_i[i]):
                    position += 1
                    label = Gtk.Label(
                        label=" => {}".format(
                            window.conflicts[_n]['head'].split("\t")[1]),
                        xalign=0)
                    label.n = _n
                    objects['conflicts_nav'].insert(label, -1)
                    window.conflicts_nav_label[_n] = objects['conflicts_nav'].get_row_at_index(position-1)
        objects['conflicts_nav'].show_all()
    else:
        objects['sentence_resize'].props.position = 0
    objects['unsolvable_conflicts'].set_text("{} unsolvable conflicts".format(bad_conflicts))
    objects['conflicts'].set_text("Total: {} conflicts".format(len(window.conflicts)))
    return

def goto_conflict(n):
    sentence_text = objects['sentence'].get_text(objects['sentence'].get_start_iter(), objects['sentence'].get_end_iter(), True)
    if len(sentence_text):
        if sentence_text.strip() != window.corpus[window.conflicts_i[window.this_conflict]].strip():
            show_dialog_ok("Changes made to this sentence were discarded.")
    window.this_conflict = n
    objects['this_conflict'].set_text("Now: {}".format(n+1))
    if objects['sentence'].get_text(objects['sentence'].get_start_iter(), objects['sentence'].get_end_iter(), True) != window.corpus[window.conflicts_i[n]]:
        objects['sentence'].set_text(window.corpus[window.conflicts_i[n]])
        objects['attachment_menu'] = Gtk.Menu()
    if window.kind == "git":
        objects['filename2'].set_text("{}: {}".format("Incoming", window.conflicts[n]['incoming_branch']))
    for i, col in enumerate(cols.split()):
        objects['left_{}'.format(col)].set_label(window.conflicts[n]['head'].split("\t")[i])
        objects['right_{}'.format(col)].set_label(window.conflicts[n]['incoming'].split("\t")[i])
    already_changed = []
    conflict_id = window.conflicts[n]['head'].split("\t")[0]
    for l, line in enumerate(window.corpus[window.conflicts_i[n]].splitlines()):
        if line.count("\t") == 9:
            id = line.split("\t")[0]
            word = line.split("\t")[1]
            if not id in already_changed:
                already_changed.append(id)
                if id == conflict_id:
                    window.token_in_conflict = line if not n in window.solved else window.solved[n]
                    token_in_conflict_changed()
                    break
    left_head = window.tokens[window.conflicts_i[n]].get(window.conflicts[n]['head'].split("\t")[6], "")
    right_head = window.tokens[window.conflicts_i[n]].get(window.conflicts[n]['incoming'].split("\t")[6], "")
    objects['left_label'].set_text('head [ {} ]'.format(left_head.split("\t")[1] if left_head else left_head))
    objects['right_label'].set_text('[ {} ] head'.format(right_head.split("\t")[1] if right_head else right_head))
    if n in window.conflicts_nav_label:
        objects['conflicts_nav'].select_row(window.conflicts_nav_label[n])
        GLib.idle_add(window.conflicts_nav_label[n].grab_focus)
    objects['save_conflict'].get_style_context().remove_class("save-conflict")
    objects['text_word'].get_style_context().remove_class("text-conflict")
    objects['text_word'].get_style_context().remove_class("text-solved")
    if not n in window.solved:
        objects['text_word'].get_style_context().add_class("text-conflict")
    else:
        objects['text_word'].get_style_context().add_class("text-solved")
    objects['sentence_button'].get_style_context().add_class("notebook-button-active")
    objects['tree_button'].get_style_context().remove_class("notebook-button-active")
    objects['sentence_container'].show()
    objects['grid_cols'].show()
    objects['tree_container'].hide()
    return

def click_button(btn):
    button = Gtk.Buildable.get_name(btn)
    
    if button == "open_git_file":
        win = FileChooserWindow()
        if win.filename:
            load_file("git", win.filename)
        return

    if button == "open_confusion":
        window.king = "confusion"
        show_dialog_ok("First, choose the file you want to edit.")
        win = FileChooserWindow()
        if win.filename:
            show_dialog_ok("Second, choose the file to which you are comparing it.")
            win2 = FileChooserWindow()
            if win.filename and win2.filename:
                show_dialog_ok("Finally, type the query to find tokens in the center of the confusion. \
Choose the attributes where we should look for confusions (between braces).\n\n\
Default:\nword = \".*\" {id,word,lemma,upos,xpos,feats,dephead,deprel,deps,misc}", True)
                query = window.userEntry
                if not query.strip():
                    return
                load_file("confusion", win.filename, win2.filename, query)
        return

    if button == "next_conflict":
        if len(window.conflicts) -1 > window.this_conflict:
            goto_conflict(window.this_conflict +1)
        else:
            goto_conflict(window.this_conflict)
        return

    if button == "previous_conflict":
        if window.this_conflict:
            goto_conflict(window.this_conflict -1)
        else:
            goto_conflict(window.this_conflict)
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
                    saved += 1
                window.corpus[i] = "\n".join(sentence)
                if window.kind == "confusion":
                    sentence = window.corpus2[i].splitlines()
                    del sentence[start:end+1]
                    for n in reversed(window.conflicts_l[l]):
                        sentence.insert(start, window.solved[n])
                    window.corpus2[i] = "\n".join(sentence)
        with open(window.filename, "w", encoding="utf-8", newline="") as f:
            f.write("\n\n".join(window.corpus))
        if window.kind == "confusion":
            with open(window.filename2, "w", encoding="utf-8", newline="") as f:
                f.write("\n\n".join(window.corpus2))
        show_dialog_ok("{} conflicts were solved and saved to \"{}\".".format(saved, window.filename))
        sys.exit()

    if button == "save_conflict":
        save_token_in_conflict()
        return

    if button == "next_unsolved":
        for n in range(len(window.conflicts)):
            if not n in window.solved:
                goto_conflict(n)
                break
        return

    if button == "copy_right":
        for col in cols.split():
            change_col(objects["right_{}".format(col)])
        return

    if button == "help":
        show_dialog_ok('Hotkeys:\n\n\
    - Ctrl + S: Save any sentence modifications you have made (you still need to click "Save and Quit" to save your changes to the actual file).\nIn case it\'s a Git merge conflict file, note that the INCOMING chunk in the sentence will be discarded, so do not edit it.\n\
    - Alt + Left / Right: Go to the previous / next conflict, discarding any changes not saved.\n\
    - Ctrl + R: Copy all attributes for this token in conflict from the file in the right.\n\
    - Ctrl + U: Find the next conflict you have yet not solved.\n\
    - Ctrl + T: Change tree/sentence visualization.\n\
    - Right click any token to choose where to attach it.\n\
                ')
        return

    if button == "tree_button":
        if not window.changed_attached and objects['tree_container'].props.visible:
            click_button(objects['sentence_button'])
            return
        sentence = (objects['sentence'].get_text(
                objects['sentence'].get_start_iter(), 
                objects['sentence'].get_end_iter(), 
                True).strip()).splitlines()
        new_sentence = []
        is_incoming = False
        for line in sentence:
            if line.startswith('<<<<<<< HEAD'):
                continue
            if line.startswith('======='):
                is_incoming = True
                continue
            if line.startswith(">>>>>>> "):
                is_incoming = False
                continue
            if not is_incoming:
                new_sentence.append(line)
        with open(os.path.dirname(os.path.abspath(__file__)) + "/sentence.conllu", "w", encoding="utf-8") as f:
            f.write("\n".join(new_sentence).strip() + "\n\n")
        try:
            output = "\n".join(draw_tree("sentence.conllu").splitlines()[1:])
        except ValueError as e:
            show_dialog_ok("{}:\n{}".format(str(e).split(": ", 1)[0], str(e).split(": ", 1)[1]))
            if objects['tree_container'].props.visible:
                click_button(objects['sentence_button'])
            return
        if not ' root' in output.splitlines()[0]:
            output = output.split("    │", 1)[1]
            output = ("────┮" + output).strip()
        else:
            output = output.split("   ╰", 1)[1]
            output = ("─────" + output).strip()
        objects['tree_viewer'].get_buffer().set_text(output)
        os.remove(os.path.dirname(os.path.abspath(__file__)) + "/sentence.conllu")
        objects['sentence_button'].get_style_context().remove_class("notebook-button-active")
        objects['tree_button'].get_style_context().add_class("notebook-button-active")
        objects['sentence_container'].hide()
        objects['tree_container'].show()
        objects['grid_cols'].hide()
        return

    if button == "sentence_button":
        objects['sentence_button'].get_style_context().add_class("notebook-button-active")
        objects['tree_button'].get_style_context().remove_class("notebook-button-active")
        objects['sentence_container'].show()
        if objects['tree_container'].props.visible:
            objects['grid_cols'].show()
        else:
            if objects['grid_cols'].props.visible:
                objects['grid_cols'].hide()
            else:
                objects['grid_cols'].show()
        objects['tree_container'].hide()
        return

def attach_token(widget):
    sentence_or_tree = "tree" if objects['tree_container'].props.visible else "sentence"
    label = widget.get_label().replace("<b>", "").replace("</b>", "")
    dephead = label.split(maxsplit=1)[0]
    sentence = objects['sentence'].get_text(objects['sentence'].get_start_iter(), objects['sentence'].get_end_iter(), True).strip().splitlines()
    for token in sentence:
        if token.count("\t") == 9 and token.split("\t")[0] == dephead:
            dephead_dephead = token.split("\t")[6]
            break
    if dephead == window.token_being_attached or dephead_dephead == window.token_being_attached:
        show_dialog_ok("Not allowed: introduces a cycle.")
        return
    for l, line in enumerate(sentence):
        if line.count("\t") == 9 and line.split("\t")[0] == window.token_being_attached:
            line = line.split("\t")
            line[6] = dephead
            line = "\t".join(line)
            sentence[l] = line
            break
    objects['sentence'].set_text("\n".join(sentence))
    if sentence_or_tree == "tree":
        window.changed_attached = True
        click_button(objects['tree_button'])
        window.changed_attached = False
    elif sentence_or_tree == "sentence":
        objects["sentence"].remove_tag_by_name(
            "reattached", objects["sentence"].get_start_iter(), objects["sentence"].get_end_iter())
        objects["sentence"].apply_tag_by_name(
            'reattached',
            objects["sentence"].get_iter_at_line(l), 
            objects["sentence"].get_iter_at_line_offset(l, len(line)))
    objects[sentence_or_tree].move_mark_by_name("reattached", objects[sentence_or_tree].get_iter_at_line(l))
    GLib.idle_add(
        objects['{}_viewer'.format(sentence_or_tree)].scroll_to_mark, objects[sentence_or_tree].get_mark("reattached"), 0.1, True, 0.0, 0.5)
    return

def attach_popup(widget, event):
    if event.button == 3:
        tree_or_sentence = Gtk.Buildable.get_name(widget).split("_")[0]
        x, y = widget.get_pointer()
        x, y = widget.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, x, y)
        iter = widget.get_iter_at_location(x, y)
        objects[tree_or_sentence].place_cursor(iter[1])
        pos = objects[tree_or_sentence].get_iter_at_mark(objects[tree_or_sentence].get_insert())
        window.token_being_attached = str(pos.get_line()+1) if tree_or_sentence == "tree" else window.corpus[window.conflicts_i[window.this_conflict]].splitlines()[pos.get_line()].split("\t")[0]
        for menu in objects['attachment_menu'].get_children():
            objects['attachment_menu'].remove(menu)
        already_appended = []
        for line in objects['sentence'].get_text(objects['sentence'].get_start_iter(), objects['sentence'].get_end_iter(), True).splitlines():
            if line.count("\t") == 9:
                id = line.split("\t")[0]
                word = line.split("\t")[1]
                if not '-' in id and not id in already_appended:
                    menu_item = Gtk.MenuItem("")
                    menu_item.connect('activate', attach_token)
                    if id == window.token_being_attached:
                        menu_item.get_children()[0].set_markup(markup_bold("<b>{} {}</b>".format(id, word)))
                    else:
                        menu_item.get_children()[0].set_label("{} {}".format(id, word))
                    objects['attachment_menu'].append(menu_item)
                    already_appended.append(id)
        objects['attachment_menu'].show_all()
        objects['attachment_menu'].popup_at_pointer()
        return True
    return False

def draw_tree(conllu):
    """Test the draw() method, which uses udapi.block.write.textmodetrees."""
    with RedirectedStdout() as out:
        doc = Document()
        data_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), conllu)
        doc.load_conllu([data_filename])
        root = doc.bundles[0].get_tree()
        root.draw(indent=4, color=False, attributes='form,upos,deprel',
                    print_sent_id=False, print_text=False, print_doc_meta=False)
        s = str(out)
    return s

class RedirectedStdout:
    def __init__(self):
        self._stdout = None
        self._string_io = None

    def __enter__(self):
        self._stdout = sys.stdout
        sys.stdout = self._string_io = StringIO()
        return self

    def __exit__(self, type, value, traceback):
        sys.stdout = self._stdout

    def __str__(self):
        return self._string_io.getvalue()

def save_token_in_conflict(btn=None):
    conflict = window.token_in_conflict.strip()
    if conflict and conflict.count("\t") == 9 and all(x.strip() for x in conflict.split("\t")):
        window.solved[window.this_conflict] = conflict
        objects['solved_conflicts'].set_text("Solved: {}".format(len(window.solved)))
        if window.this_conflict in window.conflicts_nav_label:
            conflicts_nav_label = window.conflicts_nav_label[window.this_conflict].get_children()[0].get_label()
            if not '✔' in conflicts_nav_label:
                window.conflicts_nav_label[window.this_conflict].get_children()[0].set_label("{} {}".format(conflicts_nav_label, "✔"))
    else:
        show_dialog_ok("Conflict not saved: wrong annotation format")
        return
    sentence_text = objects['sentence'].get_text(
        objects['sentence'].get_start_iter(), objects['sentence'].get_end_iter(), True).strip()
    if len(sentence_text.strip().splitlines()) != len(window.corpus[window.conflicts_i[window.this_conflict]].strip().splitlines()):
        show_dialog_ok("Sentence has different number of lines, not saving it.")
        return
    if (sentence_text.strip() and 
        all(not '\t' in x or (x.count("\t") == 9 and all(y.strip() for y in x.split("\t"))) for x in sentence_text.splitlines()) and
        window.kind != "git" or (window.kind == "git" and all(x in sentence_text for x in ["<<<<<<< HEAD", "=======", ">>>>>>>"]))):
        window.corpus[window.conflicts_i[window.this_conflict]] = sentence_text
    else:
        show_dialog_ok("Sentence modifications not saved: wrong annotation format")
        return
    click_button(objects['next_conflict'])
    return

def change_col(btn):
    col = Gtk.Buildable.get_name(btn).split("_")[1]
    c = cols.split().index(col)    
    token_in_conflict = window.token_in_conflict.split("\t")
    token_in_conflict[c] = btn.get_label()
    window.token_in_conflict = "\t".join(token_in_conflict)
    sentence_text = objects['sentence'].get_text(
        objects['sentence'].get_start_iter(), objects['sentence'].get_end_iter(), True).splitlines()
    conflict_id = window.token_in_conflict.split("\t")[0]
    for l, line in enumerate(sentence_text):
        if line.split("\t")[0] == conflict_id and sentence_text[l] != window.token_in_conflict:
            sentence_text[l] = window.token_in_conflict
            objects['sentence'].set_text("\n".join(sentence_text))
            token_in_conflict_changed()
            break
    return

def sentence_changed(textbuffer):
    objects['save_conflict'].get_style_context().add_class("save-conflict")
    conflict_id = window.token_in_conflict.split("\t")[0]
    for l, line in enumerate(
        textbuffer.get_text(textbuffer.get_start_iter(), textbuffer.get_end_iter(), True).splitlines()):
        if line.count("\t") == 9:
            if line.split("\t")[0] == conflict_id:
                if line != window.token_in_conflict:
                    window.token_in_conflict = line
                    token_in_conflict_changed(highlight=False)
                return
    return

def tree_changed(textbuffer):
    sentence = objects['sentence'].get_text(objects['sentence'].get_start_iter(), objects['sentence'].get_end_iter(), True).splitlines()
    tokens = {}
    for l, line in enumerate(
        textbuffer.get_text(textbuffer.get_start_iter(), textbuffer.get_end_iter(), True).strip().splitlines()):
        line = "".join([x for x in line if x not in "│┾╼─┮╰╭┢┶┡╪"])
        if len(line.split()) >= 3:
            upos = line.rsplit(maxsplit=2)[-2]
            deprel = line.rsplit(maxsplit=2)[-1]
            if not str(l+1) in tokens:
                tokens[str(l+1)] = (upos, deprel)
    already_changed = []
    for l, line in enumerate(sentence):
        if line.count("\t") == 9:
            id = line.split("\t")[0]
            if id in tokens and not id in already_changed:
                already_changed.append(id)
                line = line.split("\t")
                line[3] = tokens[id][0]
                line[7] = tokens[id][1]
                line = "\t".join(line)
                if line != sentence[l]:
                    sentence[l] = line
                    objects['sentence'].set_text("\n".join(sentence))
                    break
    return

def markup_underline(text):
    return html.escape(text.replace("<u>", "*u*").replace("</u>", "*/u*")).replace("*u*", "<u>").replace("*/u*", "</u>")

def markup_bold(text):
    return html.escape(text.replace("<b>", "*b*").replace("</b>", "*/b*")).replace("*b*", "<b>").replace("*/b*", "</b>")

def token_in_conflict_changed(highlight=True):
    conflict_id = window.token_in_conflict.split("\t")[0]
    text_word_id = window.token_in_conflict.split("\t")[0]
    text_word = window.token_in_conflict.split("\t")[1]
    text_left = [(y.split("\t")[1] if x != window.token_in_conflict.split("\t")[6] else "<u>{}</u>".format(y.split("\t")[1])) for x, y in window.tokens[window.conflicts_i[window.this_conflict]].items() if not '-' in x and int(x) < int(text_word_id)] if not '-' in text_word_id else ""
    text_right = [(y.split("\t")[1] if x != window.token_in_conflict.split("\t")[6] else "<u>{}</u>".format(y.split("\t")[1])) for x, y in window.tokens[window.conflicts_i[window.this_conflict]].items() if not '-' in x and int(x) > int(text_word_id)] if not '-' in text_word_id else ""
    objects['text_word'].set_label(text_word)
    objects['text_left'].set_markup(markup_underline(" ".join(text_left)))
    objects['text_right'].set_markup(markup_underline(" ".join(text_right)))
    objects['save_conflict'].get_style_context().add_class("save-conflict")
    objects['text_word'].get_style_context().remove_class("text-conflict")
    objects['text_word'].get_style_context().remove_class("text-solved")
    sentence_text = objects['sentence'].get_text(objects['sentence'].get_start_iter(), objects['sentence'].get_end_iter(), False).splitlines()
    if highlight:
        for l, line in enumerate(sentence_text):
            if line.count("\t") == 9 and line.split("\t")[0] == conflict_id:
                objects['sentence'].remove_tag_by_name(
                    "conflict", objects['sentence'].get_start_iter(), objects['sentence'].get_end_iter())
                objects['sentence'].apply_tag_by_name(
                    'conflict',
                    objects['sentence'].get_iter_at_line(l), 
                    objects['sentence'].get_iter_at_line_offset(l, len(window.token_in_conflict)))
                objects['sentence'].move_mark_by_name("conflict", objects['sentence'].get_iter_at_line(l))
                GLib.idle_add(
                    objects['{}_viewer'.format('sentence')].scroll_to_mark, objects['sentence'].get_mark("conflict"), 0.1, True, 0.0, 0.5)
                break
    head_split = window.conflicts[window.this_conflict]['head'].split("\t")
    incoming_split = window.conflicts[window.this_conflict]['incoming'].split("\t")
    token_in_conflict_split = window.token_in_conflict.split("\t")
    for i, col in enumerate(cols.split()):
        left = objects['left_{}'.format(col)].get_style_context()
        right = objects['right_{}'.format(col)].get_style_context()
        left.remove_class("solved")
        left.remove_class("conflict")
        right.remove_class("solved")
        right.remove_class("conflict")
        if (head_split[i] != incoming_split[i] or
            (head_split[i] == incoming_split[i] and
            head_split[i] != token_in_conflict_split[i])):
            if token_in_conflict_split[i] == head_split[i]:
                if not 'solved' in left.list_classes():
                    left.add_class("solved")
            else:
                if not 'conflict' in left.list_classes():
                    left.add_class("conflict")
            if token_in_conflict_split[i] == incoming_split[i]:
                if not 'solved' in right.list_classes():
                    right.add_class("solved")
            else:
                if not 'conflict' in right.list_classes():
                    right.add_class("conflict")
    return

def font_changed(btn):
    font_description = btn.get_font_desc()
    objects['sentence_viewer'].modify_font(font_description)
    window.config['font'] = btn.get_font()
    save_config()
    return

def label_font_changed(btn):
    font_description = btn.get_font_desc()
    font = btn.get_font()
    objects['text_left'].modify_font(font_description)
    objects['text_right'].modify_font(font_description)
    objects['text_word'].modify_font(Pango.FontDescription("{} {} {}".format(
        font.rsplit(" ", 1)[0],
        'Bold',
        font.rsplit(" ", 1)[1]
    )))
    window.config['label_font'] = font
    save_config()
    return

def save_config():
    with open(config_path, "w") as f:
        json.dump(window.config, f)
    return

def conflicts_nav_changed(btn, row):
    label = row.get_children()[0]
    n = label.n
    goto_conflict(int(n))
    pass

def tree_zoom(btn):
    objects['tree_viewer'].modify_font(Pango.FontDescription("{} {}".format(
        'Consolas',
        btn.get_value())))
    window.config['tree_zoom'] = btn.get_value()
    save_config()
    return

def dark_mode_changed(btn, state):
    for obj in objects:
        try:
            objects[obj].get_style_context().remove_class('light' if state else 'dark')
            objects[obj].get_style_context().add_class('dark' if state else 'light')
        except AttributeError:
            pass
    settings.set_property("gtk-application-prefer-dark-theme", state)  # if you want use dark theme, set second arg to True
    window.config['dark_mode'] = state
    objects['sentence_viewer'].set_highlight_current_line(not state)
    objects['tree_viewer'].set_highlight_current_line(not state)
    save_config()
    objects['conflict'].props.background = "yellow" if not state else "darkgrey"
    objects['conflict'].props.foreground = "black"
    return
    
builder = Gtk.Builder()
GObject.type_register(GtkSource.View)
builder.add_from_file(os.path.dirname(os.path.abspath(__file__)) + "/conllu-merge-resolver.glade")
screen = Gdk.Screen.get_default()
provider = Gtk.CssProvider()
provider.load_from_path(os.path.dirname(os.path.abspath(__file__)) + "/conllu-merge-resolver.css")
Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

settings = Gtk.Settings.get_default()

buttons = "text_word tree_button sentence_button copy_right help next_unsolved save_conflict open_git_file open_confusion \
    next_conflict previous_conflict save_changes"
other_objects = "notebook-buttons dark_mode label_font label_container grid_cols tree_zoom sentence_container tree_container conflicts_nav_grid conflicts_nav font sentence_viewer filename filename2 \
    text_left text_right conflicts this_conflict solved_conflicts unsolvable_conflicts \
    left_label right_label tree_viewer sentence_resize"
cols = "id word lemma upos xpos feats dephead deprel deps misc"

objects = {
    x: builder.get_object(x)
    for x in buttons.split() + 
    other_objects.split()
}

for button in buttons.split():
    if isinstance(objects[button], Gtk.Button):
        objects[button].connect('clicked', click_button)

for col in cols.split():
    for direction in ["left", "right"]:
        objects["{}_{}".format(direction, col)] = builder.get_object("{}_{}".format(direction, col))
        objects["{}_{}".format(direction, col)].connect('clicked', change_col)

objects['sentence'] = objects['sentence_viewer'].get_buffer()
objects['sentence'].connect('changed', sentence_changed)
objects['tree'] = objects['tree_viewer'].get_buffer()
objects['tree'].connect('changed', tree_changed)
objects['tree_viewer'].connect('button-press-event', attach_popup)
objects['conflict'] = objects['sentence'].create_tag('conflict')
objects['reattached'] = objects['sentence'].create_tag('reattached')
objects['sentence'].create_mark('conflict', objects['sentence'].get_start_iter())
objects['sentence'].create_mark('reattached', objects['sentence'].get_start_iter())
objects['tree'].create_mark('reattached', objects['tree'].get_start_iter())
objects['font'].connect('font-set', font_changed)
objects['label_font'].connect('font-set', label_font_changed)
objects['conflicts_nav'].connect('row-activated', conflicts_nav_changed)
objects['tree_zoom'].connect('value-changed', tree_zoom)
objects['dark_mode'].connect('state-set', dark_mode_changed)

window = builder.get_object("window1")
window.changed_attached = False
window.config = {}

config_path = os.path.dirname(os.path.abspath(__file__)) + "/config.json"
if os.path.isfile(config_path):
    with open(config_path) as f:
        window.config.update(json.load(f))

objects['font'].set_font(
    window.config.get(
        'font', 
        "Courier New 10" if "win" in sys.platform else "Monospace 10"))
font_changed(objects['font'])

objects['tree_zoom'].set_value(
    window.config.get(
        'tree_zoom',
        10 if 'win' in sys.platform else 10))

objects['label_font'].set_font(
    window.config.get(
        'label_font',
        'Arial 12' if 'win' in sys.platform else "Open Sans 12"))
label_font_changed(objects['label_font'])

objects['dark_mode'].props.active = window.config.get('dark_mode')
dark_mode_changed(objects['dark_mode'], objects['dark_mode'].props.active)

if len(sys.argv) == 2:
    if not os.path.isfile(sys.argv[1]):
        show_dialog_ok("Files \"{}\" does not exist.".format(sys.argv[1]))
        sys.exit()
    load_file("git", sys.argv[1])
if len(sys.argv) > 2:
    if not os.path.isfile(sys.argv[1]):
        show_dialog_ok("Files \"{}\" does not exist.".format(sys.argv[1]))
        sys.exit()
    if not os.path.isfile(sys.argv[2]):
        show_dialog_ok("Files \"{}\" does not exist.".format(sys.argv[2]))
        sys.exit()
    load_file("confusion", sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else ".*")

def on_close(x, y):
    if window.__dict__.get('unsaved') and window.solved:
        show_dialog_ok('Closing CoSMO will discard any changes you have made.\nClick "Save and Quit" to keep them or close again to discard.')
        window.unsaved = False
        return True
    Gtk.main_quit()

window.connect('delete_event', on_close)
window.connect("destroy", Gtk.main_quit)
window.show_all()

if __name__ == "__main__":
    Gtk.main()
