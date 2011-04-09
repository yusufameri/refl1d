import sqlalchemy as db
from sqlachemy.ext.declarative import declarative_base


metadata = db.MetaData()
Session = db.orm.sessionmaker(autocommit=False)
JOBDB_PATH = os.path.expanduser('~/.jobqueue.db')
def connect():
    engine = db.create_engine('sqlite:///'+JOBDB_PATH, echo=True)
    metadata.create_all(checkfirst=True)
    Session.configure(bind=engine)

STATUS = ['PENDING','ACTIVE','CANCEL','COMPLETE','ERROR']

Record = declarative_base()

class Job(Record):
    """
    *id* : Integer
        Unique id for the job
    *name* : String(80)
        Job name as specified by the user.  This need not be unique.
    *origin* : String(45)
        IP address originating the request
    *date* : DateTime
        Request submission time
    *start* : DateTime
        Time the request was processed
    *stop* : DateTime
        Time the request was completed
    *priority* : Float
        Priority level for the job
    *notify* : String(254)
        Email/twitter notification address
    *status* : PENDING|ACTIVE|CANCEL|COMPLETE|ERROR
        Job status

    The job request, result and any supplementary information are
    stored in the directory indicated by jobid.
    """

    __tablename__ = 'jobs'

    id = db.Column(db.Integer, db.Sequence('jobid_seq'), primary_key=True)
    name = db.String(80)
    origin = db.String(45) # <netinet/in.h> #define INET6_ADDRSTRLEN 46
    date = db.DateTime()
    start = db.DateTime()
    stop = db.DateTime()
    priority = db.Float()
    notify = db.String(254) # RFC 3696 errata 1690: max email=254
    status = db.Enum(*STATUS, name="status_enum")

    def __init__(self, name, origin, date, notify):
        self.status = 'PENDING'
        self.name = name
        self.origin = origin
        self.date = date
        self.notify = notify

    def __repr__(self):
        return "<Job('%s')>" % (self.name)

class ActiveJob(Record):
    """
    *id* : Integer
        Unique id for the job
    *job* : job.id
        Active job
    *queue* : String(256)
        Queue on which the job is running
    """
    __tablename__ = "active_jobs"
    id = db.Column(db.Integer, db.Sequence('activeid_seq'), primary_key=True)
    job_id = Column(Integer, ForeignKey(Job.id))
    queue = String(256)

    job = relationship(Job, uselist=False)

    def __init__(self, job, queue):
        self.job_id = job.id
        self.queue = queue

    def __repr__(self):
        return "<ActiveJob('%s','%s')>" % (self.job_id, self.queue)

class RemoteQueue(Record):
    """
    *id* : Integer
        Unique id for the remote server
    *name* : String(80)
        Name of the remote server
    *key* : String(80)
        Public key for the remote server
    """
    __tablename__ = "remote_queues"
    id = db.Column(db.Integer, db.Sequence('remotequeueid_seq'),
                   primary_key=True)
    name = db.String(80)
    key = db.String(80)