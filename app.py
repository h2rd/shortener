from flask import Flask, request, redirect, abort, Response
from flask.ext.sqlalchemy import SQLAlchemy
from gevent.pywsgi import WSGIServer
from functools import wraps

import datetime
import hashlib
import json
import random
import settings
import string

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = settings.ENGINE_URL
db = SQLAlchemy(app)


def json_view(fun):
    @wraps(fun)
    def wrapper(*args, **kwargs):
        try:
            result, status = fun(*args, **kwargs)
        except Exception as e:
            result, status = {"error": {"message": e.name, "code": e.code}}, e.code

        headers = {"Content-type": "application/json"}
        return Response(json.dumps(result), status, headers)
    return wrapper


def md5(s):
    return hashlib.md5(s).hexdigest()


def randkey(length=5):
    return ''.join(random.sample(string.letters*length, length))


class Link(db.Model):
    __tablename__ = 'links'

    key = db.Column(db.String(8), default=randkey, primary_key=True)
    url = db.Column(db.String(600))
    md5_url = db.Column(db.String(64), unique=True)
    created = db.Column(db.DateTime, default=datetime.datetime.now)
    count = db.Column(db.Integer)

    def __init__(self, url):
        self.url = url
        self.md5_url = md5(url)

    def __repl__(self):
        return 'Link(%s, %s)' % (self.key, self.url)

    @classmethod
    def find_by_key(cls, key):
        return Link.query.filter_by(key=key).first()

    @classmethod
    def find_by_url(cls, url):
        return Link.query.filter_by(md5_url=md5(url)).first()

    def json(self):
        return dict(
            key=self.key,
            url=self.url,
            created=self.created.strftime('%F %X'),
            link="%s/%s" % (settings.DOMAIN_URL, self.key),
            count=self.count or 0
        )


class Statistic(db.Model):
    __tablename__ = 'statistics'

    id = db.Column(db.Integer, primary_key=True)
    created = db.Column(db.DateTime, default=datetime.datetime.now)
    link_id = db.Column(db.String(8), db.ForeignKey('links.key'))
    user_agent = db.Column(db.String(255))
    link = db.relationship('Link', backref=db.backref('statistics',
                                                      lazy='dynamic'))

    def __init_(self, link, user_agent):
        self.user_agent = user_agent
        self.link = link

    def __repl__(self):
        return 'Stats(%s)' % (self.link_id)


@app.errorhandler(404)
@json_view
def page_not_found(error):
    return abort(404)

@app.route('/')
def main():
    return abort(404)

@app.route('/', methods=["post"])
@json_view
def add_link():
    url = request.values['url']
    link = Link.find_by_url(url)
    if not link:
        link = Link(url=url)
        db.session.add(link)
        db.session.commit()

    return link.json(), 200


@app.route('/<key>')
def redirect_to_url(key):
    link = Link.find_by_key(key)
    if not link:
        return abort(404)

    link.count = (link.count or 0) + 1
    stat = Statistic(user_agent=str(request.user_agent), link=link)
    db.session.add(stat)
    db.session.commit()

    return redirect(link.url, 301)


@app.route('/<key>+')
@json_view
def stats(key):
    link = Link.find_by_key(key)
    if not link:
        return abort(404)

    return link.json(), 200


if __name__ == '__main__':
    http = WSGIServer((settings.HOST, settings.PORT), app)
    http.serve_forever()
