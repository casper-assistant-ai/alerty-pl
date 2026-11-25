/**
 * @name Leaflet content built from data as an HTML string
 * @description Leaflet writes string tooltip and popup content through innerHTML
 *              (DivOverlay._updateContent), so a string built from data, such as the name of
 *              an OpenStreetMap object or an RCB message, runs as markup. Pass an element of
 *              h(), whose text goes through textContent, or a function that returns one.
 * @kind problem
 * @problem.severity error
 * @security-severity 6.1
 * @precision high
 * @id alerty/js/leaflet-html-content
 * @tags security
 *       external/cwe/cwe-079
 */

import javascript

/** A call of a Leaflet content sink; its first argument is the content. */
class LeafletContentCall extends DataFlow::MethodCallNode {
  LeafletContentCall() {
    this.getMethodName() =
      ["bindTooltip", "bindPopup", "setTooltipContent", "setPopupContent", "setContent"]
  }

  DataFlow::Node getContent() { result = this.getArgument(0) }
}

/** `content` is a string that the code built from data, and `why` says how. */
predicate builtFromData(DataFlow::Node content, string why) {
  // "<b>" + name, `${name} m`, [a, b].join(""): a string with a part that is not a constant
  exists(StringOps::ConcatenationRoot c |
    DataFlow::localFlowStep*(c, content) and
    exists(DataFlow::Node leaf | leaf = c.getALeaf() and not exists(leaf.getStringValue())) and
    why = "a string concatenated from data"
  )
  or
  // p.name, shelter.address: a field of a data object as it is
  content.getALocalSource() instanceof DataFlow::PropRead and
  not content.getALocalSource().asExpr() instanceof Function and
  why = "a field of a data object"
}

from LeafletContentCall call, string why
where
  builtFromData(call.getContent(), why) and
  not call.getFile().getRelativePath().matches("docs/vendor/%")
select call.getContent(),
  "Leaflet " + call.getMethodName() + " gets " + why +
    " and writes it through innerHTML. Pass an element of h() or a function that returns one."
