# Independent DS-060/061 complete-source integer state and event witness.
limit<-2147483647
integer_value<-function(x) {
  if(length(x)!=1L || !is.numeric(x) || is.nan(x)) stop('numeric type')
  if(is.na(x)) return(NA_real_)
  if(!is.finite(x) || abs(x)>limit || x!=trunc(x)) stop('integer value bound')
  if(x==0) 0 else x
}
ordinary<-function(n) grepl('^[a-z_][a-z0-9_]{0,31}$',n) && !(n %in% c('_n_','_error_','_all_','_numeric_','_character_','_temporary_','_infile_','_file_','_ods_','_page_','_blankpage_','_null_'))
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(enc2utf8(x)))),collapse='')
show<-function(x) if(is.na(x)) '.' else sprintf('%.0f',x)
match_parts<-function(pattern,text) {m<-regmatches(text,regexec(paste0('^(?:',pattern,')$'),text,perl=TRUE,ignore.case=TRUE))[[1]];if(length(m)) m[-1] else NULL}
scan_source<-function(path) {
 chars<-strsplit(paste(readLines(path,warn=FALSE),collapse='\n'),'',fixed=TRUE)[[1]];i<-1L;n<-length(chars);buffer<-'';out<-character();quote<-'';comment<-0L
 while(i<=n) {
  c<-chars[i];nextc<-if(i<n) chars[i+1L] else ''
  if(comment>0L) {if(c=='/' && nextc=='*') {comment<-comment+1L;i<-i+2L} else if(c=='*' && nextc=='/') {comment<-comment-1L;i<-i+2L;buffer<-paste0(buffer,' ')} else i<-i+1L;next}
  if(nzchar(quote)) {buffer<-paste0(buffer,c);if(c==quote) {if(nextc==quote) {buffer<-paste0(buffer,nextc);i<-i+1L} else quote<-''};i<-i+1L;next}
  if(c=='/' && nextc=='*') {comment<-1L;i<-i+2L;next}
  if(!nzchar(trimws(buffer)) && (c=='*' || c=='%' && nextc=='*')) {while(i<=n && chars[i]!=';') i<-i+1L;if(i>n) stop('comment terminator');i<-i+1L;next}
  if(c %in% c("'",'"')) {quote<-c;buffer<-paste0(buffer,c);i<-i+1L;next}
  if(c==';') {text<-trimws(buffer);if(nzchar(text)) out<-c(out,text);buffer<-''} else buffer<-paste0(buffer,if(grepl('[[:space:]]',c)) ' ' else c)
  i<-i+1L
 }
 if(nzchar(quote) || comment || nzchar(trimws(buffer))) stop('incomplete source')
 out
}
expression<-function(text,control=FALSE) {
 if(any(as.integer(charToRaw(text))>127) || nchar(text)>4096) stop('ASCII expression')
 pattern<-'[0-9]+(?:\\.[0-9]*)?(?:[eE][+-]?[0-9]+)?|\\.[0-9]+(?:[eE][+-]?[0-9]+)?|[A-Za-z_][A-Za-z0-9_]*|[.()+*-]'
 if(control) pattern<-'[0-9]+|[A-Za-z_][A-Za-z0-9_]*|[()+-]'
 locations<-gregexpr(pattern,text,perl=TRUE);tokens<-regmatches(text,locations)[[1]];positions<-as.integer(locations[[1]])
 if(control && length(tokens)>128) stop('control token budget')
 if(!length(tokens) || paste(tokens,collapse='')!=gsub('[[:space:]]','',text)) stop('expression tokens')
 at<-1L;peek<-function() if(at<=length(tokens)) tokens[at] else ''
 take<-function() {if(at>length(tokens)) stop('expression end');x<-tokens[at];at<<-at+1L;x}
 atom<-function(depth) {
  if(depth>32) stop('expression depth');x<-take()
  if(x=='(') {v<-addition(depth+1L);if(take()!=')') stop('parenthesis');return(v)}
  if(x %in% c('+','-')) {
   sign_position<-at-1L;literal<-at<=length(tokens) && grepl('^(?:[0-9]|\\.[0-9])',peek(),perl=TRUE) && positions[at]==positions[sign_position]+1L
   v<-atom(depth+1L)
   if(literal && v$kind=='number') return(list(kind='number',value=integer_value(if(x=='-') -v$value else v$value)))
   return(if(x=='+') v else list(kind='arithmetic',op='-',left=list(kind='number',value=0),right=v))
  }
  if(x=='.') return(list(kind='number',value=NA_real_))
  if(grepl('^[0-9.]',x)) return(list(kind='number',value=integer_value(as.numeric(x))))
  name<-tolower(x);if(!(ordinary(name) || name=='_n_')) stop('operand name')
  list(kind='variable',name=name)
 }
 product<-function(depth) {v<-atom(depth);while(peek()=='*') {take();v<-list(kind='arithmetic',op='*',left=v,right=atom(depth+1L))};v}
 addition<-function(depth) {v<-product(depth);while(peek() %in% c('+','-')) {op<-take();v<-list(kind='arithmetic',op=op,left=v,right=product(depth+1L))};v}
 value<-addition(1L);if(at<=length(tokens)) stop('unconsumed expression');value
}
static<-function(e,control=FALSE,depth=1L) {
 if(depth>32) stop('expression depth')
 if(e$kind=='number') {if(control && is.na(e$value)) stop('missing control');return(list(known=TRUE,value=e$value))}
 if(e$kind=='variable') return(list(known=FALSE))
 if(control && e$op=='*') stop('control arithmetic')
 a<-static(e$left,control,depth+1L);b<-static(e$right,control,depth+1L)
 if(!a$known || !b$known) return(list(known=FALSE))
 value<-if(is.na(a$value) || is.na(b$value)) NA_real_ else integer_value(switch(e$op,'+'=a$value+b$value,'-'=a$value-b$value,'*'=a$value*b$value))
 list(known=TRUE,value=value)
}
expr_names<-function(e) {if(e$kind=='variable') e$name else if(e$kind=='arithmetic') c(expr_names(e$left),expr_names(e$right)) else character()}
expr_count<-function(e) if(e$kind=='arithmetic') 1L+expr_count(e$left)+expr_count(e$right) else 0L
predicate<-function(text) {
 m<-match_parts('(.+?)\\s*(<=|>=|\\^=|~=|<>|=|<|>|\\b(?:eq|ne|lt|le|gt|ge)\\b)\\s*(.+)',text)
 if(is.null(m)) list(op='truth',left=expression(text)) else list(op=tolower(m[2]),left=expression(m[1]),right=expression(m[3]))
}
expanded<-function(text) {
 if(any(as.integer(charToRaw(text))>127)) stop('ASCII names');parts<-strsplit(trimws(gsub(' *- *','-',tolower(text))),' +')[[1]];result<-character()
 for(p in parts) {m<-match_parts('([a-z_][a-z0-9_]*?)([1-9][0-9]?)\u002d([a-z_][a-z0-9_]*?)([1-9][0-9]?)',p)
  if(is.null(m)) result<-c(result,p) else {a<-as.integer(m[2]);b<-as.integer(m[4]);if(m[1]!=m[3] || a>b || b>64) stop('range');result<-c(result,paste0(m[1],seq.int(a,b)))}
 }
 if(!length(result) || length(result)>64 || anyDuplicated(result) || any(!vapply(result,ordinary,FALSE))) stop('name list');result
}
selector<-function(text,option=FALSE) {m<-match_parts(if(option) '(keep|drop) *= *(.*)' else '(keep|drop) +(.*)',text);if(is.null(m)) stop('selection');list(mode=tolower(m[1]),names=expanded(m[2]))}
dataset<-function(text,keyword) {if(any(as.integer(charToRaw(text))>127)) stop('ASCII dataset');m<-match_parts(paste0(keyword,' +([a-z_][a-z0-9_]{0,31})(?: *\\((.*)\\))?'),text);if(is.null(m)) stop('dataset');name<-tolower(m[1]);if(!(ordinary(name) || keyword=='data' && name=='_null_')) stop('dataset name');list(name=name,selection=if(length(m)>1 && nzchar(m[2])) selector(m[2],TRUE) else NULL)}
select_names<-function(schema,s) {if(is.null(s)) return(schema);if(any(!(s$names %in% schema))) stop('unresolved selection');v<-schema[(schema %in% s$names)==(s$mode=='keep')];if(!length(v)) stop('empty selection');v}
number_spec<-function() list(type='number',length='-',label='-',format='-',keys=character())
load_catalog<-function(folder) {
 if(file.exists(file.path(folder,'invalid.flag'))) stop('catalog transport shape')
 tables<-read.csv(file.path(folder,'tables.csv'),colClasses='character',na.strings=NULL);specs<-read.csv(file.path(folder,'descriptors.csv'),colClasses='character',na.strings=NULL);values<-read.csv(file.path(folder,'values.csv'),colClasses='character',na.strings=NULL);result<-list()
 generic_name<-function(n,k) {if(k!='string' || any(as.integer(charToRaw(n))>127) || !grepl('^[A-Za-z_][A-Za-z0-9_]{0,31}$',n)) stop('generic name');tolower(n)}
 for(i in seq_len(nrow(tables))) {
  t<-tables[i,];name<-generic_name(t$table,t$table_kind);if(name %in% names(result)) stop('duplicate table name');keys<-strsplit(t$table_keys,'|',fixed=TRUE)[[1]]
  if(!all(c('schema','rows') %in% keys) || any(!(keys %in% c('schema','rows','encoding','label'))) || !(t$encoding %in% c('-','utf-8','ascii','latin-1')) || !((t$encoding_kind=='-' && t$encoding=='-') || t$encoding_kind=='string') || !(t$dataset_label_kind %in% c('-','string'))) stop('table metadata')
  result[[name]]<-list(schema=list(),rows=replicate(as.integer(t$row_count),list(),simplify=FALSE),encoding=t$encoding,label=t$dataset_label,keys=keys)
 }
 for(i in seq_len(nrow(specs))) {
  d<-specs[i,];table<-tolower(d$table);name<-generic_name(d$name,d$name_kind);if(!(table %in% names(result)) || name %in% names(result[[table]]$schema) || name %in% c('_n_','_error_')) stop('duplicate/reserved schema')
  keys<-if(d$keys=='-') character() else strsplit(d$keys,'|',fixed=TRUE)[[1]]
  if(d$type_kind!='string' || !(d$type %in% c('number','typed-number','character')) || length(keys) && (!('type' %in% keys) || any(!(keys %in% c('type','length','label','format')))) || !(d$label_kind %in% c('-','string')) || !(d$format_kind %in% c('-','string'))) stop('descriptor fields')
  if(d$type %in% c('number','typed-number')) {if(!((d$length=='-' && d$length_kind=='-') || d$length=='8' && d$length_kind=='integer')) stop('numeric width')} else {if(d$length_kind!='integer' || !grepl('^[0-9]+$',d$length) || as.numeric(d$length)<1 || as.numeric(d$length)>32767) stop('character width')}
  result[[table]]$schema[[name]]<-list(type=d$type,length=d$length,label=d$label,format=d$format,keys=keys)
 }
 for(i in seq_len(nrow(values))) {
  v<-values[i,];table<-tolower(v$table);name<-generic_name(v$name,v$name_kind);t<-result[[table]];position<-as.integer(v$row)
  if(is.null(t) || position<1 || position>length(t$rows) || !(name %in% names(t$schema)) || name %in% names(t$rows[[position]])) stop('row name/shape')
  spec<-t$schema[[name]]
  if(v$kind=='missing' && spec$type!='character') x<-NA_real_ else if(v$kind=='number' && spec$type!='character') {x<-as.numeric(v$value);if(!is.finite(x)) stop('finite generic value')} else if(v$kind=='character' && spec$type=='character') {width<-as.integer(spec$length);encoding<-if(t$encoding=='-') 'UTF-8' else if(t$encoding=='latin-1') 'latin1' else t$encoding;encoded<-iconv(v$value,from='UTF-8',to=encoding,sub=NA);if(is.na(encoded)) stop('character encoding');bytes<-nchar(encoded,type='bytes');if(bytes>width) stop('character width');x<-paste0(v$value,strrep(' ',width-bytes))} else if(v$kind=='tagged' && spec$type!='character' && grepl('^[_A-Z]$',v$value)) x<-structure(list(tag=v$value),class='sas_tag') else stop('generic imported type')
  t$rows[[position]][[name]]<-x;result[[table]]<-t
 }
 for(t in result) for(row in t$rows) if(!setequal(names(row),names(t$schema))) stop('generic row shape')
 result
}

program<-function(path,folder) {
 statements<-scan_source(path);cursor<-1L;tables<-load_catalog(folder);logs<-character();traces<-character();accounts<-list();cat('STATEMENTS:',length(statements),'\n',sep='')
 while(cursor<=length(statements)) {
  header<-dataset(statements[cursor],'data');cursor<-cursor+1L;log_offset<-length(logs);retained<-list();arrays<-list();out_selection<-header$selection;input_selection<-NULL;input_name<-NULL;feature<-FALSE;seen_action<-FALSE;op_count<-0L;math_count<-0L
  discover_expr<-function(e,control=FALSE) {static(e,control);math_count<<-math_count+expr_count(e);invisible(NULL)}
  discover_test<-function(p) {discover_expr(p$left);if(p$op!='truth') discover_expr(p$right)}
  capture_count<-function(start,stop,by) {if(is.na(start) || is.na(stop) || is.na(by) || by==0) stop('counted controls');count<-if((stop-start)*by<0) 0 else floor((stop-start)/by)+1;if(count>10000) stop('counted bound');as.integer(count)}
  parse_body<-function(depth=0L,loops=character(),active=character(),closing=FALSE) {
   if(depth>32) stop('mixed depth');body<-list()
   repeat {
    if(cursor>length(statements)) stop('missing terminator');text<-statements[cursor];cursor<<-cursor+1L
    if(tolower(text)=='end') {if(!closing) stop('unmatched END');return(body)}
    if(tolower(text)=='run') {if(closing) stop('RUN before END');return(body)}
    body[[length(body)+1L]]<-parse_one(text,depth,loops,active)
   }
  }
  parse_one<-function(text,depth,loops,active,branch=FALSE) {
   op_count<<-op_count+1L;if(depth>32 || op_count>1024 || nchar(text)>4096) stop('source bound')
   # Only quoted PUT text may contain non-ASCII bytes, and literal validation
   # below retains the existing printable-ASCII policy.
   if(any(as.integer(charToRaw(text))>127)) stop('ASCII control syntax')
   low<-tolower(text)
   if(low=='do') {feature<<-TRUE;seen_action<<-TRUE;return(list(kind='group',body=parse_body(depth+1L,loops,active,TRUE)))}
   m<-match_parts('if +(.+?) +then +(.+)',text)
   if(!is.null(m)) {seen_action<<-TRUE;p<-predicate(m[1]);discover_test(p);action<-parse_one(m[2],depth+1L,loops,active,TRUE);otherwise<-NULL
    if(cursor<=length(statements)) {other<-match_parts('else +(.+)',statements[cursor]);if(!is.null(other)) {cursor<<-cursor+1L;otherwise<-parse_one(other[1],depth+1L,loops,active,TRUE)}}
    return(list(kind='if',test=p,body=list(action),otherwise=if(is.null(otherwise)) list() else list(otherwise)))}
   if(low %in% c('leave','continue')) {if(!length(loops)) stop('transfer ownership');feature<<-TRUE;seen_action<<-TRUE;return(list(kind=low))}
   conditional<-match_parts('do +(while|until) *\\((.*)\\)',text);counted<-match_parts('do +([a-z_][a-z0-9_]{0,31}) *= *(.+?) +to +(.+?)(?: +by +(.+))?',text)
   if(!is.null(conditional) || !is.null(counted)) {
    if(branch || length(loops)>=8 || length(loops) && (is.null(counted) || any(loops!='counted'))) stop('loop nesting');seen_action<<-TRUE
    if(!is.null(conditional)) {kind<-tolower(conditional[1]);p<-predicate(conditional[2]);discover_test(p);return(list(kind=kind,test=p,body=parse_body(depth+1L,c(loops,kind),active,TRUE)))}
    index<-tolower(counted[1]);if(!ordinary(index) || index %in% active) stop('control index');terms<-c(counted[2],counted[3],if(length(counted)>3 && nzchar(counted[4])) counted[4] else '1');controls<-lapply(terms,expression,control=TRUE)
    for(e in controls) {discover_expr(e,TRUE);if(index %in% expr_names(e)) stop('self control')}
    known<-lapply(controls,static,control=TRUE);if(known[[3]]$known && known[[3]]$value==0) stop('zero BY');if(all(vapply(known,function(x) x$known,FALSE))) capture_count(known[[1]]$value,known[[2]]$value,known[[3]]$value)
    return(list(kind='counted',index=index,controls=controls,body=parse_body(depth+1L,c(loops,'counted'),c(active,index),TRUE)))}
   if(grepl('^set\\b',low,perl=TRUE)) {if(depth || branch || seen_action || !is.null(input_name)) stop('SET prefix');input<-dataset(text,'set');input_name<<-input$name;input_selection<<-input$selection;return(list(kind='read'))}
   m<-match_parts('retain +([a-z_][a-z0-9_]{0,31}) +(.+)',text)
   if(!is.null(m)) {name<-tolower(m[1]);value<-expression(m[2]);if(depth || branch || seen_action || !ordinary(name) || name %in% names(retained) || value$kind!='number' && !(value$kind=='arithmetic' && value$op=='-' && value$left$kind=='number' && value$left$value==0 && value$right$kind=='number')) stop('RETAIN literal');s<-static(value);if(!s$known) stop('RETAIN literal');retained[[name]]<<-s$value;return(list(kind='declare',name=name))}
   if(grepl('^(keep|drop)\\b',low,perl=TRUE)) {if(depth || branch || !is.null(out_selection)) stop('selector context');out_selection<<-selector(text);return(list(kind='declare_selection'))}
   seen_action<<-TRUE
   if(low=='output' || grepl('^output +',low)) {target<-if(low=='output') header$name else sub('^output +','',low);if(target!=header$name || target=='_null_') stop('OUTPUT target');return(list(kind='output'))}
   m<-match_parts('put +((?:[a-z_][a-z0-9_]{0,31} *= *)+)',text)
   if(!is.null(m)) {parts<-regmatches(tolower(m[1]),gregexpr('[a-z_][a-z0-9_]{0,31}',tolower(m[1]),perl=TRUE))[[1]];if(any(!vapply(parts,ordinary,FALSE)) || nchar(paste(paste0(parts,'=.'),collapse=' '))>64) stop('named PUT');return(list(kind='put_named',names=parts))}
   m<-match_parts('put +([a-z_][a-z0-9_]{0,31}(?: +[a-z_][a-z0-9_]{0,31})*)',text)
   if(!is.null(m)) {parts<-strsplit(tolower(m[1]),' +')[[1]];if(any(!vapply(parts,ordinary,FALSE)) || length(parts)*2>64) stop('numeric PUT');return(list(kind='put_list',names=parts))}
   if(grepl('^put +',low)) {rest<-sub('^[Pp][Uu][Tt] +','',text);pattern<-"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"";parts<-regmatches(rest,gregexpr(pattern,rest,perl=TRUE))[[1]];if(!length(parts) || nzchar(trimws(gsub(pattern,'',rest,perl=TRUE)))) stop('literal PUT');values<-vapply(parts,function(p) {q<-substr(p,1,1);b<-substr(p,2,nchar(p)-1);if(q=='"' && grepl('[&%]',b)) stop('macro quote');if(!nzchar(b)) q else gsub(paste0(q,q),q,b,fixed=TRUE)},'');value<-paste0(values,collapse='');if(nchar(value)>64 || any(as.integer(charToRaw(value))<32 | as.integer(charToRaw(value))>126)) stop('literal text');return(list(kind='put_literal',value=value))}
   m<-match_parts('if +(.+)',text)
   if(!is.null(m)) {if(length(loops)) stop('loop subset');p<-predicate(m[1]);discover_test(p);return(list(kind='subset',test=p))}
   assignment<-match_parts('([a-z_][a-z0-9_]{0,31}) *= *(.+)',text);summation<-match_parts('([a-z_][a-z0-9_]{0,31}) *\\+ *(.+)',text)
   if(!is.null(assignment) || !is.null(summation)) {m<-if(!is.null(assignment)) assignment else summation;name<-tolower(m[1]);if(!ordinary(name) || name %in% active) stop('assignment name');e<-expression(m[2]);discover_expr(e);if(is.null(assignment) && !(name %in% names(retained))) retained[[name]]<<-0;return(list(kind=if(is.null(assignment)) 'sum' else 'assign',name=name,value=e))}
   stop(paste('unsupported statement',text))
  }
  body<-parse_body();if(!feature || math_count>128) stop('profile feature/expression bound');schema<-list();source<-NULL;puts<-list();explicit<-FALSE
  add<-function(name) if(name!='_n_' && is.null(schema[[name]])) schema[[name]]<<-number_spec()
  discover<-function(body) for(op in body) {
   if(op$kind=='read') {source<<-tables[[input_name]];if(is.null(source)) stop('SET absent');names<-select_names(names(source$schema),input_selection);source$schema<<-source$schema[names];source$rows<<-lapply(source$rows,function(row) row[names]);if(length(source$rows)>10000) stop('SET rows');for(n in names) {if(!ordinary(n) || !(source$schema[[n]]$type %in% c('number','typed-number'))) stop('SET numeric');schema[[n]]<<-source$schema[[n]]};for(row in source$rows) for(x in row) integer_value(x)}
   if(op$kind %in% c('declare','assign','sum')) add(op$name)
   if(op$kind=='counted') {add(op$index);for(e in op$controls) for(n in expr_names(e)) add(n)}
   if(!is.null(op$value) && is.list(op$value)) for(n in expr_names(op$value)) add(n)
   if(!is.null(op$test)) {for(n in expr_names(op$test$left)) add(n);if(op$test$op!='truth') for(n in expr_names(op$test$right)) add(n)}
   if(op$kind=='output') explicit<<-TRUE
   if(op$kind %in% c('put_named','put_list')) puts[[length(puts)+1L]]<<-op
   if(!is.null(op$body)) discover(op$body)
   if(!is.null(op$otherwise)) discover(op$otherwise)
  }
  discover(body);if(!length(schema) || length(schema)>64) stop('PDV bound');chosen<-select_names(names(schema),out_selection)
  for(op in puts) for(n in op$names) if(!(n %in% names(schema)) || !(schema[[n]]$format %in% c('-',''))) stop('PUT complete unformatted schema')
  input<-if(is.null(source)) list(list()) else source$rows;output<-list();events<-0L;trips<-0L;iteration<-0L
  event<-function(...) {events<<-events+1L;if(events>1000000) stop('event budget');traces<<-c(traces,paste(...,sep='|'))}
  eval<-function(e) {if(e$kind=='number') return(e$value);if(e$kind=='variable') return(integer_value(if(e$name=='_n_') iteration else row[[e$name]]));a<-eval(e$left);b<-eval(e$right);if(is.na(a) || is.na(b)) NA_real_ else integer_value(switch(e$op,'+'=a+b,'-'=a-b,'*'=a*b))}
  test<-function(p) {a<-eval(p$left);if(p$op=='truth') return(!is.na(a) && a!=0);b<-eval(p$right);if(is.na(a) || is.na(b)) {if(is.na(a) && is.na(b)) {a<-0;b<-0} else {if(is.na(a)) a<- -Inf;if(is.na(b)) b<- -Inf}};switch(p$op,'='=a==b,eq=a==b,ne=a!=b,'^='=a!=b,'~='=a!=b,'<>'=a!=b,'<'=a<b,lt=a<b,'<='=a<=b,le=a<=b,'>'=a>b,gt=a>b,'>='=a>=b,ge=a>=b)}
  snapshot<-function() {if(length(output)>=10000) stop('OUTPUT bound');output[[length(output)+1L]]<<-row[chosen];event('output',paste(vapply(chosen,function(n) paste0(n,'=',show(row[[n]])),''),collapse=';'))}
  perform<-function(body) {
   for(op in body) {
    kind<-op$kind
    if(kind %in% c('declare','read','declare_selection')) next
    if(kind=='assign') {row[[op$name]]<<-eval(op$value);event('assign',op$name,show(row[[op$name]]))}
    else if(kind=='sum') {x<-eval(op$value);old<-row[[op$name]];row[[op$name]]<<-integer_value((if(is.na(x)) 0 else x)+(if(is.na(old)) 0 else old));event('sum',op$name,show(row[[op$name]]))}
    else if(kind=='group') {event('group','enter');signal<-perform(op$body);event('group','exit');if(signal!='normal') return(signal)}
    else if(kind=='if') {value<-test(op$test);event('if',as.integer(value));signal<-perform(if(value) op$body else op$otherwise);if(signal!='normal') return(signal)}
    else if(kind=='subset') {value<-test(op$test);event('subset',as.integer(value));if(!value) return('reject')}
    else if(kind %in% c('leave','continue')) {event('transfer',kind);return(kind)}
    else if(kind=='counted') {controls<-vapply(op$controls,eval,0.0);for(x in controls) integer_value(x);count<-capture_count(controls[1],controls[2],controls[3]);spent<<-spent+count;if(spent>10000) stop('shared counted budget');row[[op$index]]<<-integer_value(controls[1]);event('capture',op$index,show(controls[1]),show(controls[2]),show(controls[3]),count);left<-FALSE
     if(count) for(k in seq_len(count)) {value<-controls[1]+(k-1)*controls[3];row[[op$index]]<<-integer_value(value);trips<<-trips+1L;event('iteration','counted',op$index,show(value));signal<-perform(op$body);if(signal=='reject') return(signal);if(signal=='leave') {left<-TRUE;break};row[[op$index]]<<-integer_value(value+controls[3]);event('increment',op$index,show(row[[op$index]]))}
     if(!left) row[[op$index]]<<-integer_value(controls[1]+count*controls[3]);event('loop','exit','counted')}
    else if(kind %in% c('while','until')) {local<-0L;repeat {if(kind=='while') {value<-test(op$test);event('test','while',as.integer(value));if(!value) break};local<-local+1L;if(local>10000) stop('conditional budget');trips<<-trips+1L;event('iteration',kind,local);signal<-perform(op$body);if(signal=='reject') return(signal);if(signal=='leave') break;if(kind=='until') {value<-test(op$test);event('test','until',as.integer(value));if(value) break}};event('loop','exit',kind)}
    else if(kind=='output') snapshot()
    else if(kind %in% c('put_named','put_list','put_literal')) {if(length(logs)-log_offset>=10000) stop('PUT count');text<-if(kind=='put_literal') op$value else if(kind=='put_named') paste(vapply(op$names,function(n) paste0(n,'=',show(row[[n]])),''),collapse=' ') else paste0(paste(vapply(row[op$names],show,''),collapse=' '),' ');if(nchar(text)>64) stop('PUT width');logs<<-c(logs,text);event('put',hex(text))}
    else stop('unhandled action')
   }
   'normal'
  }
  for(incoming in input) {iteration<-iteration+1L;spent<-0L;row<-setNames(as.list(rep(NA_real_,length(schema))),names(schema));row[names(retained)]<-retained;for(n in names(incoming)) row[[n]]<-integer_value(incoming[[n]]);event('row',iteration);signal<-perform(body);if(signal %in% c('leave','continue')) stop('escaped transfer');retained<-row[names(retained)];if(signal=='normal' && !explicit && header$name!='_null_') snapshot()}
  table<-list(schema=schema[chosen],rows=output,encoding=if(is.null(source)) '-' else source$encoding,label=if(is.null(source)) '-' else source$label,keys=c(if(is.null(source)) character() else source$keys[!(source$keys %in% c('schema','rows'))],'schema','rows'))
  if(header$name!='_null_') tables[[header$name]]<-table
  accounts[[length(accounts)+1L]]<-list(name=header$name,iterations=iteration,trips=trips)
 }
 for(name in names(tables)) {
  t<-tables[[name]];cat('TABLE:',name,'\nMETA:',t$encoding,'|',t$label,'\nTABLEKEYS:',paste(t$keys,collapse='|'),'\n',sep='')
  for(n in names(t$schema)) {d<-t$schema[[n]];cat('COLUMN:',paste(c(n,d$type,d$length,d$label,d$format),collapse='|'),'\n',sep='');if(length(d$keys)) cat('COLUMNKEYS:',paste(c(n,d$keys),collapse='|'),'\n',sep='')}
  for(row in t$rows) {cat('ROWKEYS:',paste(names(row),collapse='|'),'\n',sep='');cat('ROW:',paste(vapply(row,function(x) if(inherits(x,'sas_tag')) paste0('T',x$tag) else if(is.character(x)) paste0('C',hex(x)) else if(is.na(x)) 'M' else paste0('N',sprintf('%.17g',x)),''),collapse=','),'\n',sep='')}
 }

 for(a in accounts) cat('ACCOUNT:',a$name,',',a$iterations,',',a$trips,'\n',sep='')
 for(l in logs) cat('LOG:',hex(l),'\n',sep='')
 for(t in traces) cat('TRACE:',hex(t),'\n',sep='')
}
args<-commandArgs(trailingOnly=TRUE)
if(length(args)==3 && args[1]=='program') program(args[2],args[3]) else if(length(args)==2 && args[1]=='batch') {
 cases<-read.csv(file.path(args[2],'cases.csv'),colClasses='character')
 for(i in seq_len(nrow(cases))) {cat('CASE:',i-1L,'\n',sep='');good<-tryCatch({program(file.path(args[2],cases$source[i]),file.path(args[2],cases$catalog[i]));TRUE},error=function(e) {cat('REASON:',conditionMessage(e),'\n',sep='');FALSE});cat('ANSWER:',if(good) 'OK' else 'REFUSE','\n',sep='')}
} else stop('program source catalog-folder or batch folder')
