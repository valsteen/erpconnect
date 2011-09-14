# -*- coding: utf-8 -*-
import xmlrpclib
from operator import itemgetter

class OpenERP(object):
    def __init__(self, host, db, login, password):
        self.db = db
        self.login = login
        self.password = password
        sock_common = xmlrpclib.ServerProxy ('http://%s:8069/xmlrpc/common' % host)
        self.uid = sock_common.login(db, login, password)
        self.queries = {}
        self._modules = {}

        self.sock = xmlrpclib.ServerProxy('http://%s:8069/xmlrpc/object' % host)

        for model in self["ir.model"].search(fields=["model"]):
            parts = model["model"].split(".")

            for num, part in enumerate(parts):
                name = ".".join(parts[:num+1])
                if not name in self._modules:
                    if (num+1) == len(parts):
                        getter = Query(self, name)
                    else:    
                        getter = ModelGetter(self, name)
                    self._modules[name] = getter
                    setattr(self, name, getter)
                else:
                    getter = self._modules[name]

                if num > 0:
                    prev = ".".join(parts[:num])
                    setattr(self._modules[prev], part, getter)

    _lang = None
    def get_context(self, context=None):
        if context is None: context = {}
        _context = {}
        if self._lang: _context["lang"] = self._lang
        _context.update(context)
        return _context

    def execute(self, *params, **argv):
        all_params = [self.db, self.uid, self.password]
        all_params.extend(params)
        return self.sock.execute(*all_params, **argv)

    def __getitem__(self, openobject):
        if openobject in self.queries: return self.queries[openobject]
        
        query = Query(self, openobject)
        self.queries[openobject] = query
        return query

    def __getattribute__(self, modulename):
        try:
            return super(OpenERP, self).__getattribute__(modulename)
        except:
            if modulename not in self._modules:
                self._modules[modulename] = ModelGetter(self,modulename)

            return self._modules[modulename]

class ModelGetter(object):
    def __init__(self, erpconnector, modulename):
        self.modulename = modulename
        self.erpconnector = erpconnector

    def __getattribute__(self, modelname):
        try:
            return super(ModelGetter, self).__getattribute__(modelname)
        except:
            return self.erpconnector[self.modulename + "." + modelname]

class F(object):
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name

    def __lt__(self, name):
        return Condition([self.name,"<",name])

    def __gt__(self, name):
        return Condition([self.name,">",name])

    def __eq__(self, name):
        if isinstance(name, (list, tuple)):
            return Condition([self.name,"in",name])
        else:
            return Condition([self.name,"=",name])

    def __ne__(self, name):
        if isinstance(name, (list, tuple)):
            return Condition([self.name,"not in",name])
        else:
            return Condition([self.name,"<>",name])

    def like(self, name):
        return Condition([self.name, "like", name])

class Query(object):
    _model_fields = {}

    def __init__(self, openerp, openobject):
        self.__foreignkeys = {}
        self._foreignkeys= self.__foreignkeys
        self.__init_done = False
        self._openerp = openerp
        self._openobject = openobject

        super(Query, self).__init__()

    def execute(self, command, *params, **argv):
        return self._openerp.execute(self._openobject, command, *params, **argv)

    def _tolist(self, conditions):
        res = []
        for condition in conditions:
            if isinstance(condition, list):
                condition = self._tolist(condition)
            res.append(condition)
        return res

    def raw_search(self, domain, **params):
        context = params.get("context", {})
        context = self._openerp.get_context(context)
            
        return self._openerp.execute(self._openobject, 'search', self._tolist(domain), params.get("offset",0), params.get("limit", False), params.get("order",False), context)

    def __foreignkeys__(self):
        if hasattr(self, "checkforeignkeys") and not self.__init_done:
            self.__init_done = True

            if not self._openobject in self._model_fields:
                self._model_fields[self._openobject] = self.__foreignkeys
                for field in self._openerp["ir.model.fields"].search([('model','=',self._openobject),('relation','!=','')], fields=["name","relation"]):
                    self.__foreignkeys[field["name"]] = field["relation"]
        
        
    def read(self, ids, fields=False, context=None, as_dict=False, with_audit=False):
        self.__foreignkeys__()
        context = self._openerp.get_context(context)

        query = self
        class UpdatableList(list):
            def write(self, changes):
                return query.write(map(itemgetter('id'), res), changes)

            def unlink(self):
                return query.unlink(map(itemgetter('id'), res))

        res = self._openerp.execute(self._openobject, 'read', ids, fields, context)

        if with_audit:
            audit_res = dict((rec["id"], rec) for rec in self._openerp.execute(self._openobject, 'perm_read', ids, context, False))

        if res:
            if with_audit:
                for rec in res:
                    rec.update(audit_res.get(rec["id"],{}))

            for column, model in self.__foreignkeys.items():
                if column not in res[0]: continue

                for rec in res:
                    if not isinstance(rec[column], (tuple, list)): continue
                    if len(rec[column]) > 1 and not isinstance(rec[column][1], (int, long)) :
                        parent = self._openerp[model].read([rec[column][0]])
                        if parent: rec[column] = parent[0]
                        else: rec[column] = False
                    else:
                        rec[column] = self._openerp[model].read(rec[column])
        
        if as_dict:
            field = isinstance(as_dict, basestring) and as_dict or "id"
            return dict((i["id"], i) for i in res)

        return UpdatableList(res)

    def search(self, domain=[], **params):
        context = params.pop("context", {})
        context = self._openerp.get_context(context)
        as_dict = params.pop("as_dict", False)
        with_audit = params.pop("with_audit", False)
        fields = params.pop("fields", False)
        return self.read(self.raw_search(domain, context=context, **params), fields, context, as_dict=as_dict, with_audit=with_audit)

    def count(self, domain=[], **params):
        context = params.pop("context", {})
        context = self._openerp.get_context(context)
        return self._openerp.execute(self._openobject, 'search', self._tolist(domain), params.get("offset",0), params.get("limit", False), params.get("order",False), context, True)

    def write(self, ids, changes, context=None):
        context = self._openerp.get_context(context)
        return self._openerp.execute(self._openobject, 'write', ids, changes, context)

    def unlink(self, ids, context=None):
        context = self._openerp.get_context(context)
        return self._openerp.execute(self._openobject, 'unlink', ids, context)

    def create(self, values, context=None):
        context = self._openerp.get_context(context)
        return self._openerp.execute(self._openobject, 'create', values, context)

    def __setitem__(self, column, value):
        self.__foreignkeys[column] = value

    def ___getattribute__(self, name):
        try:
            return super(Query, self).__getattribute__(name)
        except:
            return self._openerp[self._openobject + "." + name]

class Condition(list):
    def __and__(self, condition):
        if self[0] in "&":
            return Condition(self + [Condition(condition)])
        else:
            return Condition(["&", self, condition])

    def __or__(self, condition):
        if self[0] in "|":
            return Condition(self + [Condition(condition)])
        else:
            return Condition(["|", self, condition])
