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
ARXIV_RE = re.compile(r'arxiv\.org\/[a-z]+\/([0-9\.]+)')


class Parser:

    def __init__(self, dobsidian, tree):
        self.dobsidian = dobsidian
        self.tree = tree

    def parse_and_create_entry(self, url, download_pdf=False, **defaults):
        out = defaults.copy()
        out['url'] = url
        parse = self.parse(url)
        out.update(parse)
        self.create_entry(download_pdf=download_pdf, **out)

    def parse(url):
        raise NotImplementedError()

    def create_entry(self, url, title, authors, preprint, abstract, pdf, download_pdf=False):
        dout = pathlib.Path(self.dobsidian, self.tree)
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
            annotation_pdf = '{}/pdfs/{}'.format(self.tree, filename.replace(':', ''))
    
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


class OpenReviewParser(Parser):

    def parse(self, url):
        client = openreview.Client('https://api.openreview.net', username=os.environ.get('OPENREVIEW_USERNAME'), password=os.environ.get('OPENREVIEW_PASSWORD'))
        xs = OPENREVIEW_RE.findall(url)
        if not xs:
            raise ValueError('Could not find ID from {}'.format(url))
        x = xs[0]

        paper = client.get_note(x)
        title = paper.content['title']
        authors = paper.content['authors']
        abstract = paper.content['abstract']
        pdf = 'https://openreview.net/{}'.format(paper.content['pdf'].lstrip('/'))
        ret = dict(url=url, title=title, authors=authors, abstract=abstract, pdf=pdf)
        if 'preprint' in paper.content:
            ret['preprint'] = paper.content['preprint']
        return ret


class ArxivParser(Parser):

    def parse(self, url):
        xs = [x.strip('.') for x in ARXIV_RE.findall(url)]
        if not xs:
            raise ValueError('Could not find ID from {}'.format(url))
        x = xs[0]
        search = arxiv.Search(id_list=[x])
        paper = next(search.results())

        url = paper.entry_id
        title = paper.title
        authors = [a.name for a in paper.authors]
        abstract = paper.summary
        pdf = paper.pdf_url + '.pdf'
        return dict(url=url, title=title, authors=authors, abstract=abstract, pdf=pdf)


class PDFParser(Parser):

    def parse(self, url):
        response = urllib.request.urlopen(url)
        data = response.read()
        ret = {}
        with tempfile.NamedTemporaryFile(delete=True) as ftmp:
            ftmp.write(data)
            ftmp.flush()
            with open(ftmp.name, 'rb') as f:
                reader = PyPDF2.PdfFileReader(f)
                info = reader.getDocumentInfo()
                if info.author:
                    ret['authors'] = [a.strip() for a in info.author.split(';')]
                if info.title:
                    ret['title'] = info.title
                ret['pdf'] = url
        return ret


def main():
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('url', help='URL to download from.')
    parser.add_argument('--silent', action='store_true', help='print debug info.')
    parser.add_argument('--obsidian', default='{}/notes/Research'.format(os.environ['HOME']), help='where is your Obsidian root.')
    parser.add_argument('--tree', default='Papers', help='subtree of your Obsidian where papers are stored.')
    parser.add_argument('--download_pdf', action='store_true', help='download a local copy of the PDF.')
    parser.add_argument('--mode', choices=('auto', 'arxiv', 'openreview', 'pdf'), default='auto', help='force a parse mode.')
    parser.add_argument('--authors', default='unknown', help='default author list, delimited by ;')
    parser.add_argument('--title', default='unknown', help='default title')
    parser.add_argument('--abstract', default='unknown', help='default abstract')
    parser.add_argument('--preprint', default='unsorted', help='default preprint')
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

    P = dict(
        openreview=OpenReviewParser,
        arxiv=ArxivParser,
        pdf=PDFParser,
    )[mode]
    parser = P(args.obsidian, args.tree)

    defaults = dict(
        authors=[a.strip() for a in args.authors.split(';')],
        title=args.title,
        abstract=args.abstract,
        preprint=args.preprint,
    )
    parser.parse_and_create_entry(args.url, download_pdf=args.download_pdf, **defaults)


if __name__ == '__main__':
    main()
