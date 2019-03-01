import asyncio
import csv
from functools import update_wrapper
import itertools
import json
import os
import shlex
import shutil
from urllib import request

import aiohttp
from bs4 import BeautifulSoup
import click
import jinja2
import pbr.version


def coroutine(f):
    f = asyncio.coroutine(f)

    def wrapper(*args, **kwargs):
        # we can use asyncio.run(main()) with python 3.7+
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(f(*args, **kwargs))

    return update_wrapper(wrapper, f)


def read_students(students):
    result = dict()
    reader = csv.reader(students)
    for row in reader:
        result[str(row[1])] = row[0]
    return result


class Row:
    @staticmethod
    def filter_data(submission):
        arr = submission.contents[0].split('/')
        student_id = arr[-2]
        percentage = arr[-1].strip('()% ')
        url = submission['href']
        return student_id, percentage, url

    def __init__(self, match_id, submissions):
        self.match_id = match_id
        self.left_id, self.left_percentage, self.url = self.filter_data(submissions[0])
        self.right_id, self.right_percentage, _ = self.filter_data(submissions[1])


async def parse_moss_result(session, moss_url):
    async with session.get(moss_url) as response:
        html = await response.read()
        soup = BeautifulSoup(html, 'lxml')
        matches = soup.find_all('tr')[1:]
        match_dict = dict()
        for i, match in enumerate(matches):
            submissions = match.find_all('a')
            row = Row(i, submissions)
            if row.left_id not in match_dict:
                match_dict[row.left_id] = dict()
            match_dict[row.left_id][row.right_id] = row
            if row.right_id not in match_dict:
                match_dict[row.right_id] = dict()
            match_dict[row.right_id][row.left_id] = row
        return match_dict


async def download_file(session, url, filename, verbose):
    async with session.get(url) as response:
        with open(filename, 'wb') as f_handle:
            while True:
                chunk = await response.content.read(1024)
                if not chunk:
                    break
                f_handle.write(chunk)
        if verbose:
            print('Downloaded: %s => %s' % (url, filename))
        return await response.release()


def generate_download_match_tasks(session, output_dir, match_id, match_url, verbose):
    base_url = match_url.rstrip('.html')
    # print(match_id, base_url)
    suffixes = ['.html', '-top.html', '-0.html', '-1.html']
    tasks = []
    for suffix in suffixes:
        url = base_url + suffix
        filename = 'matches/match%d%s' % (match_id, suffix)
        filename = os.path.join(output_dir, filename)
        tasks.append(download_file(session, url, filename, verbose))
    return tasks


async def generate_hc_letter(session, matches, output_dir, verbose):
    tasks = []

    for row in matches:
        tasks += generate_download_match_tasks(session, output_dir, row.match_id, row.url, verbose)
    await asyncio.gather(*tasks)

    output_path = os.path.abspath(os.path.join(output_dir, 'letter.tex'))
    command = 'xelatex -shell-escape -synctex=1 -interaction=nonstopmode %s' % output_path
    args = shlex.split(command)
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, cwd=output_dir)
    if verbose:
        print('Compiling:', command, '(pid = ' + str(process.pid) + ')')
    stdout, stderr = await process.communicate()


def get_version():
    return pbr.version.VersionInfo('jiautohc')


@click.command()
@click.option('-i', '--input', required=True, type=click.File(), help='JSON file with Honor Code results')
@click.option('-o', '--output', default='output', show_default=True, type=click.Path(), help='Letters output directory')
@click.option('-t', '--template', type=click.Path(), help='TeX template [default: builtin template]')
@click.option('-s', '--students', required=True, type=click.File(), help='CSV file with student names and ids')
@click.option('-v', '--verbose', is_flag=True, help='Display verbose information')
@click.option('--serial', is_flag=True, help='Process data in serial [default: in parallel]')
@click.version_option(version=get_version())
@coroutine
async def main(input, output, template, students, verbose, serial):
    """A tool automatically sending someone to the honor council."""
    output = os.path.abspath(output)
    if not os.path.exists(output):
        os.mkdir(output)

    if not template:
        template = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'template')
    template_dir = template
    with open(os.path.join(template_dir, 'template.tex')) as file:
        template = jinja2.Template(file.read())

    config = json.load(input)
    if 'students' not in config:
        config['students'] = dict()

    if students:
        config['students'].update(read_students(students))

    hc_tasks = list()
    async with aiohttp.ClientSession() as session:

        for case in config['cases']:
            match_dict = await parse_moss_result(session, case['moss'])
            for i, match in enumerate(case['matches']):
                output_match = '%s-%s-%s-%d' % (
                    config['info']['course'], config['info']['semester'], case['shortname'], i)
                print('Started: %s' % output_match)
                output_match = os.path.join(output, output_match.lower())
                if os.path.exists(output_match):
                    shutil.rmtree(output_match)
                shutil.copytree(template_dir, output_match)
                os.mkdir(os.path.join(output_match, 'matches'))

                matches = list()
                for a, b in itertools.combinations(match['students'], 2):
                    a = str(a)
                    b = str(b)
                    if a in match_dict and b in match_dict[a]:
                        row = match_dict[a][b]
                        matches.append(row)
                matches.sort(key=lambda x: x.match_id)

                students = list()
                for student in match['students']:
                    if 'ignore' in match and student in match['ignore']:
                        continue
                    students.append({
                        'name': config['students'].get(str(student), None),
                        'id': student
                    })

                with open(os.path.join(output_match, 'letter.tex'), 'w') as file:
                    file.write(template.render(
                        info=config['info'],
                        reporter=config['reporter'],
                        students=students,
                        case=case,
                        source=match.get('source', None),
                        matches=matches,
                        version=get_version(),
                    ))

                hc_task = generate_hc_letter(session, matches, output_match, verbose)
                if serial:
                    await hc_task
                else:
                    hc_tasks.append(asyncio.ensure_future(hc_task))

        await asyncio.gather(*hc_tasks)


if __name__ == '__main__':
    # pylint: disable=no-value-for-parameter
    main()
