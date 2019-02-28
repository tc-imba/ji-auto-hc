import asyncio
import csv
import json
import os
import shutil
import shlex
from urllib import request
import itertools
from functools import update_wrapper

import aiohttp
from bs4 import BeautifulSoup
import click
import jinja2


def read_students(students):
    result = dict()
    reader = csv.reader(students)
    for row in reader:
        result[str(row[1])] = row[0]
    return result


class Row():
    def filter_data(self, submission):
        arr = submission.contents[0].split('/')
        student_id = arr[-2]
        percentage = arr[-1].strip('()% ')
        url = submission['href']
        return student_id, percentage, url

    def __init__(self, match_id, submissions):
        self.match_id = match_id
        self.left_id, self.left_percentage, self.url = self.filter_data(submissions[0])
        self.right_id, self.right_percentage, _ = self.filter_data(submissions[1])


def parse_moss_result(moss_url):
    def filter_data(data):
        arr = data.contents[0].split('/')
        student_id = arr[-2]
        percentage = arr[-1].strip('()% ')
        url = data['href']
        return student_id, percentage, url

    with request.urlopen(moss_url) as html:
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


async def download_file(session, url, filename):
    async with session.get(url) as response:
        with open(filename, 'wb') as f_handle:
            while True:
                chunk = await response.content.read(1024)
                if not chunk:
                    break
                f_handle.write(chunk)
        return await response.release()


def generate_download_match_tasks(session, output_dir, match_id, match_url):
    base_url = match_url.rstrip('.html')
    # print(match_id, base_url)
    suffixes = ['.html', '-top.html', '-0.html', '-1.html']
    tasks = []
    for suffix in suffixes:
        url = base_url + suffix
        filename = 'matches/match%d%s' % (match_id, suffix)
        filename = os.path.join(output_dir, filename)
        tasks.append(download_file(session, url, filename))
    return tasks


async def generate_hc_letter(matches, output_dir):
    tasks = []
    async with aiohttp.ClientSession() as session:
        for row in matches:
            tasks += generate_download_match_tasks(session, output_dir, row.match_id, row.url)
        await asyncio.gather(*tasks)

    command = 'xelatex -shell-escape -synctex=1 -interaction=nonstopmode %s -cd' % os.path.join('letter.tex')
    args = shlex.split(command)
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, cwd=output_dir)
    print('Started:', args, '(pid = ' + str(process.pid) + ')')
    stdout, stderr = await process.communicate()


def coroutine(f):
    f = asyncio.coroutine(f)

    def wrapper(*args, **kwargs):
        # we can use asyncio.run(main()) with python 3.7+
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(f(*args, **kwargs))

    return update_wrapper(wrapper, f)


@click.command()
@click.option('-o', '--output', default='output', show_default=True, type=click.Path(),
              help='Honor council letters output directory')
@click.option('-i', '--input', required=True, type=click.File())
@click.option('-t', '--template', default='template.tex', show_default=True, type=click.File())
@click.option('-s', '--students', type=click.File())
@coroutine
async def main(input, output, template, students):
    """A tool automatically sending someone to the honor council."""
    output = os.path.abspath(output)
    if not os.path.exists(output):
        os.mkdir(output)

    config = json.load(input)
    if 'students' not in config:
        config['students'] = dict()

    if students:
        config['students'].update(read_students(students))

    def form_student(student_id):
        return {
            'name': config['students'].get(str(student_id), None),
            'id': student_id
        }

    # print(config['students'])

    template = jinja2.Template(template.read())
    working_dir = os.getcwd()

    for case in config['cases']:
        match_dict = parse_moss_result(case['moss'])
        for i, match in enumerate(case['matches']):
            output_match = '%s-%s-%s-%d' % (config['info']['course'], config['info']['semester'], case['shortname'], i)
            output_match = os.path.join(output, output_match.lower())
            if os.path.exists(output_match):
                shutil.rmtree(output_match)
            os.makedirs(os.path.join(output_match, 'matches'))

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
                ))

            await generate_hc_letter(matches, output_match)

    # print(template.render(**config))
    # print(config['course'])
    pass


if __name__ == '__main__':
    # pylint: disable=no-value-for-parameter
    main()
