# -*- coding: utf-8 -*-
import xmlrpclib

class OpenERP(object):
    def __init__(self, host, db, login, password):
        self.db = db
        self.login = login
        self.password = password
        sock_common = xmlrpclib.ServerProxy ('http://%s:8069/xmlrpc/common' % host)
        self.uid = sock_common.login(db, login, password)

        self.sock = xmlrpclib.ServerProxy('http://%s:8069/xmlrpc/object' % host)

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

    queries = {}
    def __getitem__(self, openobject):
        if openobject in self.queries: return self.queries[openobject]
        openerp = self
        
        class Query(object):
            def execute(self, command, *params, **argv):
                return openerp.execute(openobject, command, *params, **argv)

            def raw_search(self, *domain, **params):
                context = params.get("context", {})
                context = openerp.get_context(context)
                return openerp.execute(openobject, 'search', domain, params.get("offset",0), params.get("limit", False), params.get("order",False), context)

            def read(self, ids, fields=False, context=None):
                context = openerp.get_context(context)

                query = self
                class UpdatableList(list):
                    def write(self, changes):
                        ids = [item['id'] for item in res]
                        return query.write(ids, changes)

                res = openerp.execute(openobject, 'read', ids, fields, context)

                if res:
                    for column, model in self.__foreignkeys.items():
                        if column not in res[0]: continue

                        for rec in res:
                            if not isinstance(rec[column], (tuple, list)): continue
                            if len(rec[column]) > 1 and not isinstance(rec[column][1], (int, long)) :
                                parent = openerp[model].read([rec[column][0]])
                                if parent: rec[column] = parent[0]
                                else: rec[column] = False
                            else:
                                rec[column] = openerp[model].read(rec[column])
                    
                return UpdatableList(res)

            def search(self, *domain, **params):
                context = params.pop("context", {})
                context = openerp.get_context(context)
                fields = params.pop("fields", False)
                return self.read(self.raw_search(*domain, context=context, **params), fields, context)

            def write(self, ids, changes, context=None):
                context = openerp.get_context(context)
                return openerp.execute(openobject, 'write', ids, changes, context)

            __foreignkeys = {}
            def __setitem__(self, column, value):
                self.__foreignkeys[column] = value

        query = Query()
        self.queries[openobject] = query
        return query
