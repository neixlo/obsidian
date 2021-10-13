#!/usr/bin/env python
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import os
import re
import pathlib
import tempfile
import arxiv
import openreview
import PyPDF2
import urllib.request


OPENREVIEW_RE = re.compile(r'\?id=(\S+)')
ARXIV_RE = re.compile(r'abs/([0-9\.]+)')


def parse_open_review(url, dobsidian, tree, download_pdf=False):
    client = openreview.Client('https://api.openreview.net')
    xs = OPENREVIEW_RE.findall(url)
    if not xs:
        raise ValueError('Could not find ID from {}'.format(url))
    x = xs[0]

    paper = client.get_note(x)
    title = paper.content['title']
    authors = paper.content['authors']
    abstract = paper.content['abstract']
    preprint = paper.content.get('preprint', 'unsorted')
    pdf = 'https://openreview.net/{}'.format(paper.content['pdf'].lstrip('/'))

    create_entry(url, title, authors, preprint, abstract, dobsidian, tree, pdf, download_pdf=download_pdf)


def parse_arxiv(url, dobsidian, tree, download_pdf=False):
    xs = ARXIV_RE.findall(url)
    if not xs:
        raise ValueError('Could not find ID from {}'.format(url))
    x = xs[0]
    search = arxiv.Search(id_list=[x])
    paper = next(search.results())

    url = paper.entry_id
    title = paper.title
    authors = [a.name for a in paper.authors]
    abstract = paper.summary
    preprint = 'unsorted'
    pdf = paper.pdf_url + '.pdf'
    create_entry(url, title, authors, preprint, abstract, dobsidian, tree, pdf, download_pdf=download_pdf)


def parse_pdf(url, dobsidian, tree, download_pdf=False):
    response = urllib.request.urlopen(url)
    data = response.read()
    with tempfile.NamedTemporaryFile(delete=True) as ftmp:
        ftmp.write(data)
        ftmp.flush()
        with open(ftmp.name, 'rb') as f:
            reader = PyPDF2.PdfFileReader(f)
            info = reader.getDocumentInfo()
            authors = [a.strip() for a in info.author.split(';')]
            title = info.title
            abstract = ''
            preprint = 'unsorted'
            pdf = url
    if not authors:
        raise Exception('Could not parse authors from PDF')
    if not title:
        raise Exception('Could not parse title from PDF')
    create_entry(url, title, authors, preprint, abstract, dobsidian, tree, pdf, download_pdf=download_pdf)


def create_entry(url, title, authors, preprint, abstract, dobsidian, tree, pdf, download_pdf=False):
    dout = pathlib.Path(dobsidian, tree)
    filename = '{} --- {}.pdf'.format(','.join(authors), title)
    fpdf = dout.joinpath('pdfs', filename)

    if not fpdf.parent.exists():
        os.makedirs(fpdf.parent)

    annotation_pdf = pdf
    if download_pdf:
        dpdfs = dout.joinpath('pdfs')
        if not dpdfs.exists():
            os.makedirs(dpdfs)
        response = urllib.request.urlopen(pdf)
        data = response.read()
        with open(dpdfs.joinpath(filename.replace(':', '')), 'wb') as f:
            f.write(data)
        annotation_pdf = '{}/pdfs/{}'.format(tree, filename.replace(':', ''))

    lines = [
        '---',
        'annotation-target: {}'.format(annotation_pdf),
        '---',
        '',
        '# {}'.format(title),
        '',
        'Authors',
    ]
    for a in authors:
        lines.append('- {}'.format(a))
    lines.extend([
        '',
        'URL {}'.format(url),
        'PDF {}'.format(pdf),
        '',
        '## Abstract',
        abstract,
    ])

    if not dout.joinpath(preprint).exists():
        os.makedirs(dout.joinpath(preprint))

    with dout.joinpath(preprint, '{}.md'.format(title)).open('wt') as f:
        for line in lines:
            f.write(line + '\n')


def main():
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('url', help='URL to download from.')
    parser.add_argument('--silent', action='store_true', help='print debug info.')
    parser.add_argument('--obsidian', default='{}/notes/Research'.format(os.environ['HOME']), help='where is your Obsidian root.')
    parser.add_argument('--tree', default='Papers', help='subtree of your Obsidian where papers are stored.')
    parser.add_argument('--download_pdf', action='store_true', help='download a local copy of the PDF.')
    parser.add_argument('--mode', choices=('auto', 'arxiv', 'openreview', 'pdf'), default='auto', help='force a parse mode.')
    args = parser.parse_args()

    mode = args.mode
    if mode == 'auto':
        if 'openreview' in args.url:
            mode = 'openreview'
        elif 'arxiv' in args.url:
            mode = 'arxiv'
        else:
            mode = 'pdf'
    if not args.silent:
        print('parsing {} from {}'.format(mode, args.url))

    parse = dict(
        openreview=parse_open_review,
        arxiv=parse_arxiv,
        pdf=parse_pdf,
    )[mode]
    parse(args.url, args.obsidian, args.tree, download_pdf=args.download_pdf)


if __name__ == '__main__':
    main()
