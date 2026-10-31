# Independent complete-source D2b witness, with exact dyadic arithmetic.
# Repository/base-R evidence only; ASCII/LF bytes are a named tool policy.
args<-commandArgs(trailingOnly=TRUE)
self<-sub('^--file=','',grep('^--file=',commandArgs(),value=TRUE)[1]);here<-dirname(normalizePath(self))
# The earlier R scanner and exact input conversion remain independent of Python.
prior<-readLines(file.path(here,'inline_csv.R'),warn=FALSE)
cut<-grep('^program <- function',prior)[1]
eval(parse(text=prior[seq_len(cut-1)]))

reserved<-c('_n_','_error_','_all_','_numeric_','_character_','_temporary_','_infile_','_file_','_ods_','_page_','_blankpage_','_null_')
ordinary<-function(x) is.character(x)&&length(x)==1&&all(as.integer(charToRaw(x))<128)&&grepl('^[a-z_][a-z0-9_]{0,31}$',x,perl=TRUE)&&!(x %in% reserved)
bounded<-function(x) {if(is.na(x)) return(NA_real_);if(!is.finite(x)||abs(x)>2147483647) stop('numeric magnitude');if(x==0) 0 else x}
# Bit vectors describe finite binary64 values exactly. No Python plan or host
# aggregation is used to decide whether a candidate operation rounded.
dyad<-function(x) {
  if(x==0) return(list(sign=1,bits=numeric(),exp=0))
  text<-sprintf('%a',abs(x));pieces<-strsplit(text,'p',fixed=TRUE)[[1]]
  mantissa<-sub('^0x','',pieces[1]);after<-if(grepl('.',mantissa,fixed=TRUE)) nchar(strsplit(mantissa,'.',fixed=TRUE)[[1]][2]) else 0
  digits<-strsplit(gsub('.','',mantissa,fixed=TRUE),'',fixed=TRUE)[[1]]
  bits<-unlist(lapply(rev(digits),function(d) as.numeric(intToBits(strtoi(d,16L)))[1:4]))
  normalize_dyad(list(sign=if(x<0)-1 else 1,bits=bits,exp=as.numeric(pieces[2])-4*after))
}
normalize_dyad<-function(d) {
  b<-d$bits
  while(length(b)&&tail(b,1)==0) b<-head(b,-1)
  while(length(b)&&b[1]==0) {b<-b[-1];d$exp<-d$exp+1}
  if(!length(b)) return(list(sign=1,bits=numeric(),exp=0))
  d$bits<-b;d
}
integer_bits<-function(values) {
  if(!length(values)) return(numeric())
  out<-values;i<-1L
  while(i<=length(out)) {
    carry<-floor(out[i]/2);out[i]<-out[i]%%2
    if(carry) {if(i==length(out)) out<-c(out,carry) else out[i+1]<-out[i+1]+carry}
    i<-i+1L
  }
  out
}
compare_bits<-function(a,b) {
  while(length(a)&&tail(a,1)==0) a<-head(a,-1)
  while(length(b)&&tail(b,1)==0) b<-head(b,-1)
  if(length(a)!=length(b)) return(sign(length(a)-length(b)))
  if(!length(a)) return(0)
  at<-which(rev(a)!=rev(b));if(!length(at)) 0 else sign(rev(a)[at[1]]-rev(b)[at[1]])
}
add_dyad<-function(a,b) {
  exponent<-min(a$exp,b$exp);x<-c(rep(0,a$exp-exponent),a$bits);y<-c(rep(0,b$exp-exponent),b$bits)
  width<-max(length(x),length(y));length(x)<-width;length(y)<-width;x[is.na(x)]<-0;y[is.na(y)]<-0
  if(a$sign==b$sign) return(normalize_dyad(list(sign=a$sign,bits=integer_bits(x+y),exp=exponent)))
  cmp<-compare_bits(x,y)
  if(cmp==0) return(dyad(0))
  if(cmp<0) {z<-x;x<-y;y<-z;sgn<-b$sign} else sgn<-a$sign
  borrow<-0;out<-numeric(width)
  if(width) for(i in seq_len(width)) {v<-x[i]-y[i]-borrow;borrow<-if(v<0) 1 else 0;out[i]<-v+2*borrow}
  normalize_dyad(list(sign=sgn,bits=out,exp=exponent))
}
multiply_dyad<-function(a,b) {
  if(!length(a$bits)||!length(b$bits)) return(dyad(0))
  out<-numeric(length(a$bits)+length(b$bits))
  for(i in seq_along(a$bits)) for(j in seq_along(b$bits)) out[i+j-1]<-out[i+j-1]+a$bits[i]*b$bits[j]
  normalize_dyad(list(sign=a$sign*b$sign,bits=integer_bits(out),exp=a$exp+b$exp))
}
same_dyad<-function(a,b) identical(a$sign,b$sign)&&identical(as.numeric(a$bits),as.numeric(b$bits))&&a$exp==b$exp
arithmetic<-function(a,b,op) {
  if(op!='/'&&(is.na(a)||is.na(b))) return(NA_real_)
  if(is.na(a)||is.na(b)) stop('division needs ordinary numbers')
  result<-bounded(switch(op,'+'=a+b,'-'=a-b,'*'=a*b,'/'={if(b==0) stop('zero divisor');a/b},stop('operator')))
  desired<-if(op %in% c('+','-')) add_dyad(dyad(a),dyad(if(op=='-') -b else b)) else if(op=='*') multiply_dyad(dyad(a),dyad(b)) else multiply_dyad(dyad(result),dyad(b))
  observed<-if(op=='/') dyad(a) else dyad(result)
  if(!same_dyad(desired,observed)) stop('rounded arithmetic')
  result
}
literal<-function(text) {
  if(text=='.') return(NA_real_)
  if(!grepl('^[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?$',text,perl=TRUE)) stop('numeric literal')
  bounded(as.numeric(text))
}
expand_list<-function(text,limit=64L) {
  if(any(as.integer(charToRaw(text))>127)) stop('ASCII names')
  rest<-tolower(trimws(text));terms<-character();names<-character()
  while(nzchar(rest)) {
    m<-regmatches(rest,regexec('^([a-z_][a-z0-9_]{0,31})(?:\\s*-\\s*([a-z_][a-z0-9_]{0,31}))?(?=\\s|$)',rest,perl=TRUE))[[1]]
    if(!length(m)) stop('full numeric list')
    first<-m[2];last<-if(length(m)>2) m[3] else ''
    if(nzchar(last)) {
      a<-regmatches(first,regexec('^([a-z_][a-z0-9_]*?)([0-9]+)$',first,perl=TRUE))[[1]]
      b<-regmatches(last,regexec('^([a-z_][a-z0-9_]*?)([0-9]+)$',last,perl=TRUE))[[1]]
      if(!length(a)||!length(b)||a[2]!=b[2]||nchar(a[3])>2||nchar(b[3])>2||startsWith(a[3],'0')||startsWith(b[3],'0')) stop('range spelling')
      lo<-as.integer(a[3]);hi<-as.integer(b[3])
      if(lo<1||hi>64||lo>hi||length(names)+hi-lo+1>limit) stop('range bounds')
      expanded<-paste0(a[2],seq.int(lo,hi));terms<-c(terms,paste0(first,'-',last))
    } else {expanded<-first;terms<-c(terms,first)}
    if(length(names)+length(expanded)>limit||any(!vapply(expanded,ordinary,FALSE))||any(expanded %in% names)) stop('list duplicate/name')
    names<-c(names,expanded);rest<-trimws(substring(rest,nchar(m[1])+1))
  }
  if(!length(names)||length(terms)>limit) stop('list size')
  list(names=names,terms=terms,range=any(grepl('-',terms,fixed=TRUE)))
}
file_name<-function(name) {
  if(nchar(name,type='bytes')>64||!grepl('^[A-Za-z_][A-Za-z0-9_-]*\\.[cC][sS][vV]$',name,perl=TRUE)) stop('destination')
  stem<-tolower(substr(name,1,nchar(name)-4))
  if(stem %in% c('con','prn','aux','nul',paste0('com',1:9),paste0('lpt',1:9))) stop('device')
  name
}
render_list<-function(values,comma=FALSE) {
  fields<-vapply(values,function(x) {if(is.na(x)) '.' else {if(!is.finite(x)||abs(x)>99999999999||x!=trunc(x)) stop('integer rendering');sprintf('%.0f',if(x==0)0 else x)}},'')
  text<-if(comma) paste(fields,collapse=',') else paste0(paste0(fields,' '),collapse='')
  if(nchar(text,type='bytes')>64) stop('record width')
  text
}

program<-function(path) {
  parsed<-scan_program(path);statements<-vapply(parsed$statements,normalize_code,'');at<-1L;lines<-character();exports<-list();all_logs<-character();steps<-0L
  while(at<=length(statements)) {
    header<-capture('data\\s+([a-z_][a-z0-9_]{0,31})(?:\\s*\\(\\s*(keep|drop)\\s*=\\s*(.+)\\s*\\))?',statements[at]);at<-at+1L
    if(is.null(header)) stop('DATA header')
    target<-tolower(header[1]);if(target!='_null_'&&!ordinary(target)) stop('DATA name')
    selected<-if(length(header)>1&&nzchar(header[2])) list(mode=tolower(header[2]),names=expand_list(header[3])$names) else NULL
    schema<-character();retained<-list();body<-list();input<-NULL;infile<-NULL;records<-NULL;file<-NULL;explicit<-FALSE;hasrange<-FALSE;seen_action<-FALSE;nodes<-0L;opcount<-0L;data_seen<-FALSE
    add<-function(name) {if(!ordinary(name)) stop('ordinary numeric name');if(!(name %in% schema)) schema<<-c(schema,name);if(length(schema)>64) stop('PDV cap')}
    code_guard<-function(text) {
      if(nchar(text,type='bytes')>4096||any(as.integer(charToRaw(text))>127)) stop('code size/ASCII')
      cleaned<-gsub("'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"",'',text,perl=TRUE)
      depth<-0L
      for(ch in strsplit(cleaned,'',fixed=TRUE)[[1]]) {depth<-depth+(ch=='(')-(ch==')');if(depth>32) stop('source depth')}
      if(length(regmatches(cleaned,gregexpr('[+*/-]|[A-Za-z_][A-Za-z0-9_]*\\s*\\(',cleaned,perl=TRUE))[[1]])>128) stop('source nodes')
    }
    list_value<-function(text) {
      values<-expand_list(text)
      if(any(!(values$names %in% schema))) stop('unresolved numeric list')
      hasrange<<-hasrange||values$range;values
    }
    pe<-function(text,depth=1L,allow_list=FALSE) {
      text<-tolower(trimws(text));original_text<-text
      repeat {
        if(!startsWith(text,'(')||!endsWith(text,')')) break
        chars<-strsplit(text,'',fixed=TRUE)[[1]];level<-0;complete<-TRUE
        for(i in seq_along(chars)) {level<-level+(chars[i]=='(')-(chars[i]==')');if(level==0&&i<length(chars)) complete<-FALSE}
        if(!complete||level!=0) break
        text<-trimws(substr(text,2,nchar(text)-1))
      }
      nodes<<-nodes+1L;if(nodes>128||depth>32) stop('expression nodes/depth')
      sumlist<-capture('sum\\s*\\(\\s*of\\s+(.+)\\)',text)
      if(!is.null(sumlist)) {if(!allow_list||depth!=1||original_text!=text) stop('whole SUM assignment only');return(list(kind='list',names=list_value(sumlist)$names,known=FALSE))}
      if(text=='_n_') return(list(kind='name',name=text,known=FALSE))
      if(grepl('^[a-z_][a-z0-9_]{0,31}$',text,perl=TRUE)) {if(!ordinary(text)||!(text %in% schema)) stop('unresolved numeric reference');return(list(kind='name',name=text,known=FALSE))}
      if(grepl('^[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?$|^\\.$',text,perl=TRUE)) {x<-literal(text);return(list(kind='literal',value=x,known=TRUE))}
      chars<-strsplit(text,'',fixed=TRUE)[[1]];level<-0L;positions<-integer()
      for(operators in list(c('+','-'),c('*','/'))) {
        positions<-integer();level<-0L
        for(i in seq_along(chars)) {
          ch<-chars[i]
          if(ch=='(') level<-level+1L else if(ch==')') level<-level-1L
          else if(level==0&&ch %in% operators) {
            before<-trimws(if(i>1) paste(chars[seq_len(i-1)],collapse='') else '')
            if(!nzchar(before)||grepl('[+*/(-]$',before)||ch %in% c('+','-')&&grepl('(?:[0-9.]|[0-9][0-9.]*)[eE]$',before,perl=TRUE)) next
            positions<-c(positions,i)
          }
        }
        if(length(positions)) break
      }
      if(!length(positions)) stop('unsupported expression')
      i<-tail(positions,1);left<-pe(substr(text,1,i-1),depth+1L);right<-pe(substring(text,i+1),depth+1L);op<-chars[i]
      if(op=='/'&&right$known&&!is.na(right$value)&&right$value==0) stop('static zero divisor')
      known<-left$known&&right$known;v<-if(known) arithmetic(left$value,right$value,op) else NA_real_
      list(kind='arithmetic',op=op,left=left,right=right,known=known,value=v)
    }
    predicate<-function(text) {
      prior_nodes<-nodes
      direct<-tryCatch(pe(text),error=function(e) NULL)
      if(!is.null(direct)) return(list(op='truth',left=direct))
      nodes<<-prior_nodes
      m<-capture('(.+?)\\s*(<=|>=|\\^=|~=|<>|=|<|>|\\beq\\b|\\bne\\b|\\blt\\b|\\bgt\\b|\\ble\\b|\\bge\\b)\\s*(.+)',text)
      if(is.null(m)) stop('predicate')
      list(op=tolower(m[2]),left=pe(m[1]),right=pe(m[3]))
    }
    one<-function(text,branch=FALSE,depth=0L) {
      if(depth>32) stop('IF depth')
      opcount<<-opcount+1L;if(opcount>1024) stop('operation cap')
      test<-capture('if\\s+(.+?)\\s+then\\s+(.+)',text)
      if(!is.null(test)) {
        seen_action<<-TRUE;test_node<-predicate(test[1]);child<-one(test[2],TRUE,depth+1L);result<-list(kind='if',condition=test_node,body=child)
        if(at<=length(statements)) {
          other<-capture('else\\s+(.+)',statements[at])
          if(!is.null(other)) {at<<-at+1L;result$otherwise<-one(other,TRUE,depth+1L)}
        }
        return(result)
      }
      assign<-capture('([a-z_][a-z0-9_]{0,31})\\s*(=|\\+)\\s*(.+)',text)
      if(!is.null(assign)) {
        seen_action<<-TRUE;name<-tolower(assign[1]);add(name);value<-pe(assign[3],allow_list=assign[2]=='=')
        if(assign[2]=='+'&&is.null(retained[[name]])) retained[[name]]<<-0
        return(list(kind=if(assign[2]=='+')'sum' else 'assign',name=name,value=value))
      }
      f<-capture('file\\s+([\x27\"])([^\x27\"]+)\\1\\s+dlm\\s*=\\s*([\x27\"]),\\3',text)
      if(!is.null(f)) {
        if(branch||!is.null(file)||!is.null(input)||seen_action) stop('FILE prefix')
        file<<-file_name(f[2]);return(list(kind='file'))
      }
      read<-capture('input\\s+(.+)',text)
      if(!is.null(read)) {
        if(branch||!is.null(input)||seen_action) stop('INPUT prefix')
        input<<-expand_list(read,32L)$names;for(n in input) add(n);return(list(kind='input'))
      }
      keep<-capture('retain\\s+([a-z_][a-z0-9_]{0,31})\\s+(.+)',text)
      if(!is.null(keep)) {
        if(branch||seen_action) stop('RETAIN prefix')
        name<-tolower(keep[1]);if(!is.null(retained[[name]])) stop('duplicate RETAIN');add(name);retained[[name]]<<-literal(keep[2]);return(list(kind='declare'))
      }
      selector<-capture('(keep|drop)\\s+(.+)',text)
      if(!is.null(selector)) {if(branch||!is.null(selected)) stop('projection');selected<<-list(mode=tolower(selector[1]),names=expand_list(selector[2])$names);return(list(kind='projection'))}
      seen_action<<-TRUE
      put<-capture('put\\s+(.+)',text)
      if(!is.null(put)) {
        if(substr(put,1,1) %in% c("'",'"')) return(list(kind='literal',value=put_literals(put)))
        listed<-list_value(put)$names;render_list(rep(NA_real_,length(listed)),!is.null(file));return(list(kind='put',names=listed))
      }
      out<-capture('output(?:\\s+([a-z_][a-z0-9_]{0,31}))?',text)
      if(!is.null(out)) {if(target=='_null_'||length(out)&&nzchar(out)&&tolower(out)!=target) stop('OUTPUT target');explicit<<-TRUE;return(list(kind='output'))}
      subset<-capture('if\\s+(.+)',text)
      if(!is.null(subset)) {if(branch) stop('subset IF position');return(list(kind='subset',condition=predicate(subset)))}
      stop('unsupported action')
    }
    if(!is.null(selected)) {body<-c(list(list(kind='projection')),body);opcount<-opcount+1L}
    ended<-FALSE
    while(at<=length(statements)) {
      text<-statements[at];position<-at;at<-at+1L
      if(tolower(text)=='run') {ended<-TRUE;break}
      code_guard(text)
      if(data_seen) stop('code after inline data')
      if(tolower(text) %in% c('datalines','cards')) {if(is.null(input)||is.null(parsed$records[[as.character(position)]])) stop('inline source');records<-parsed$records[[as.character(position)]];data_seen<-TRUE;next}
      opts<-capture('infile\\s+(.+)',text)
      if(!is.null(opts)) {if(!is.null(infile)||!is.null(input)||seen_action) stop('INFILE prefix');infile<-infile_options(text);next}
      body[[length(body)+1L]]<-one(text)
    }
    if(!ended||!is.null(input)&&is.null(records)||is.null(input)&&!is.null(infile)) stop('complete step')
    if(!is.null(file)&&length(exports)) stop('one export destination per program')
    selected_names<-schema
    if(!is.null(selected)) {if(any(!(selected$names %in% schema))) stop('unresolved selection');selected_names<-schema[(schema %in% selected$names)==(selected$mode=='keep')];if(!length(selected_names)) stop('empty selection')}
    rows<-if(is.null(input)) list(numeric()) else read_numeric(records,length(input),if(is.null(infile))' ' else infile$delimiter,if(is.null(infile))1L else infile$firstobs)
    if(!is.null(input)&&any(!vapply(body[seq_len(which(vapply(body,function(x)x$kind=='input',FALSE))-1)],function(x)x$kind %in% c('declare','projection','file'),FALSE))) stop('INPUT first action')
    output<-list();logs<-character();written<-character();saved<-retained;events<-0L;opens<-0L;attempts<-0L;reads<-0L
    value<-function(e) {
      if(e$kind=='literal') return(e$value)
      if(e$kind=='name') return(row[[e$name]])
      if(e$kind=='list') {total<-NA_real_;for(n in e$names) {v<-row[[n]];if(!is.na(v)) total<-if(is.na(total)) v else arithmetic(total,v,'+')};return(total)}
      arithmetic(value(e$left),value(e$right),e$op)
    }
    yes<-function(t) {
      a<-value(t$left);if(t$op=='truth') return(!is.na(a)&&a!=0)
      b<-value(t$right);if(is.na(a)) a<- -Inf;if(is.na(b)) b<- -Inf
      switch(t$op,'='=a==b,eq=a==b,'^='=a!=b,'~='=a!=b,'<>'=a!=b,ne=a!=b,'<'=a<b,lt=a<b,'>'=a>b,gt=a>b,'<='=a<=b,le=a<=b,'>='=a>=b,ge=a>=b,stop('comparison'))
    }
    perform<-function(op) {
      events<<-events+1L;if(events>1000000) stop('event cap')
      if(op$kind=='file') opens<<-opens+1L
      else if(op$kind=='input') attempts<<-attempts+1L
      else if(op$kind=='assign') row[[op$name]]<<-value(op$value)
      else if(op$kind=='sum') {a<-row[[op$name]];b<-value(op$value);row[[op$name]]<<-arithmetic(if(is.na(a))0 else a,if(is.na(b))0 else b,'+')}
      else if(op$kind=='if') {if(yes(op$condition)) return(perform(op$body));if(!is.null(op$otherwise)) return(perform(op$otherwise))}
      else if(op$kind=='subset') return(yes(op$condition))
      else if(op$kind=='output') {if(length(output)>=10000) stop('output cap');output[[length(output)+1L]]<<-row[selected_names]}
      else if(op$kind %in% c('literal','put')) {
        text<-if(op$kind=='literal')op$value else render_list(vapply(op$names,function(n)row[[n]],0.0),!is.null(file))
        if(!is.null(file)) {if(length(written)>=10000) stop('record cap');written<<-c(written,text)} else {if(length(logs)>=10000) stop('log cap');logs<<-c(logs,text)}
      } else if(!(op$kind %in% c('declare','projection'))) stop('execution kind')
      TRUE
    }
    iterations<-if(is.null(input))1L else length(rows)+1L
    for(index in seq_len(iterations)) {
      row<-setNames(as.list(rep(NA_real_,length(schema))),schema);row[names(saved)]<-saved;row[['_n_']]<-as.numeric(index)
      if(!is.null(input)) {
        source_position<-which(vapply(body,function(x)x$kind=='input',FALSE))
        if(source_position>1) for(op in body[seq_len(source_position-1)]) perform(op)
        perform(body[[source_position]])
        if(index>length(rows)) break
        reads<-reads+1L;row[input]<-as.list(rows[[index]])
        actions<-if(source_position<length(body))body[seq.int(source_position+1,length(body))] else list()
      } else actions<-body
      alive<-TRUE;for(op in actions) if(!perform(op)) {alive<-FALSE;break}
      saved<-row[names(retained)]
      if(alive&&!explicit&&target!='_null_') {if(length(output)>=10000) stop('output cap');output[[length(output)+1L]]<-row[selected_names]}
    }
    steps<-steps+1L
    lines<-c(lines,paste0('STEP:',target),paste0('SCHEMA:',paste(selected_names,collapse=',')),paste0('READS:',reads),paste0('ATTEMPTS:',attempts),paste0('OPENS:',opens),paste0('WRITES:',length(written)),paste0('EVENTS:',events))
    if(target!='_null_') for(r in output) lines<-c(lines,paste0('ROW:',encoded_rows(list(r))))
    for(log in logs) lines<-c(lines,paste0('LOG:',hex(log)))
    if(!is.null(file)) {text<-if(length(written))paste0(paste(written,collapse='\n'),'\n') else '';exports[[file]]<-text;lines<-c(lines,paste0('EXPORT:',hex(file),':',hex(text)))}
  }
  cat(paste(c(paste0('STATEMENTS:',length(statements)),lines),collapse='\n'),'\n',sep='')
}
if(args[1]=='program') program(args[2]) else if(args[1]=='batch') {
  paths<-readLines(args[2],warn=FALSE)
  for(i in seq_along(paths)) {
    cat('CASE:',i,'\n',sep='');answer<-tryCatch(list(ok=TRUE,lines=capture.output(program(paths[i]))),error=function(e) list(ok=FALSE,lines=character()))
    if(answer$ok) for(line in answer$lines) cat(line,'\n',sep='')
    cat('ANSWER:',if(answer$ok)'OK' else 'REFUSE','\n',sep='')
  }
} else stop('mode')
